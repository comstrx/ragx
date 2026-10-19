from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import ClassVar

from core.context import context
from core.database import Blueprint, Model, Query, Relation, Schema, belongs_to_many, database
from core.error import Code, Fault, error
from core.http import App
from core.queue import MemoryDriver, Queue
from core.rand import Uuid, rand
from core.test import expect, test
import asyncio, pytest

@dataclass(frozen=True, slots=True, kw_only=True)
class Note(Model):

    table      : ClassVar[str] = f"scratch_notes_{rand.hex(3)}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id   : Uuid
    body : str

def notes () -> Query[Note]:

    return Query(Note, database)

@pytest.fixture
async def table ( app: App ) -> AsyncIterator[str]:

    def define ( blueprint: Blueprint ) -> None:

        blueprint.id()
        blueprint.string("body", 80)

    async with database.transaction() as session: await Schema(session).create(Note.table, define)

    try: yield Note.table
    finally:

        async with database.transaction() as session: await Schema(session).drop(Note.table)

@pytest.mark.anyio
class TestTransactions:

    async def test_queries_join_the_ambient_transaction_and_savepoints_roll_back_alone ( self, table: str ) -> None:

        expect((database.in_transaction(), database.level())).equals((False, 0))

        async with database.transaction():

            await notes().create({ "body": "kept" })

            expect((database.in_transaction(), database.level(), await notes().count())).equals((True, 1, 1))

            with test.fails(Code.CONFLICT, "nested"):

                async with database.transaction():

                    expect(database.level()).equals(2)

                    await notes().create({ "body": "dropped" })

                    expect(await notes().count()).equals(2)

                    error.throw(Code.CONFLICT, "nested")

            expect(await notes().pluck("body")).equals(["kept"])

        expect(await notes().pluck("body")).equals(["kept"])

        with test.fails(Code.CONFLICT, "outer"):

            async with database.transaction():

                await notes().create({ "body": "gone" })

                error.throw(Code.CONFLICT, "outer")

        with test.raises(ZeroDivisionError):

            async with database.transaction():

                await notes().create({ "body": "also gone" })

                _ = 1 / 0

        expect((await notes().count(), database.in_transaction())).equals((1, False))

    async def test_jobs_leave_only_after_commit_and_never_after_rollback ( self, table: str ) -> None:

        own   = Queue()
        calls: list[str] = []

        async def remember ( body: str ) -> None:

            calls.append(body)

        own.setup(MemoryDriver(), ("default",), tries=1)

        async with database.transaction():

            await notes().create({ "body": "a" })

            pushed = await own.push(remember, "committed")

            expect((await own.size(), context.deferred.pending())).equals((0, 1))

        expect((await own.size(), pushed.queue)).equals((1, "default"))

        with test.fails(Code.CONFLICT):

            async with database.transaction():

                await own.push(remember, "rolled back")

                async with database.transaction(): await own.push(remember, "nested")

                error.throw(Code.CONFLICT)

        expect(await own.size()).equals(1)

        async with database.transaction():

            with test.fails(Code.BAD_REQUEST):

                async with database.transaction():

                    await own.push(remember, "inner dropped")

                    error.throw(Code.BAD_REQUEST)

            async with database.transaction(): await own.push(remember, "inner kept")

        expect((await own.drain(), calls)).equals((2, ["committed", "inner kept"]))

        await own.push(remember, "direct")

        expect(await own.size()).equals(1)

    async def test_after_commit_failures_surface_once_the_data_is_safe ( self, table: str ) -> None:

        ran: list[str] = []

        async def broken () -> None:

            ran.append("broken")

            raise error.unavailable("mailer")

        with test.fails(Code.UNAVAILABLE, "mailer"):

            async with database.transaction():

                await notes().create({ "body": "safe" })
                await database.after_commit(broken)
                await database.after_commit(lambda: ran.append("next"))

        expect((ran, await notes().where("body", "safe").count())).equals((["broken", "next"], 1))
        expect(await database.after_commit(lambda: ran.append("now"))).false()
        expect(ran[-1]).equals("now")

    async def test_atomic_retries_only_serialization_and_deadlocks ( self, table: str ) -> None:

        tries: list[int] = []

        async def contended () -> int:

            tries.append(1)

            await notes().create({ "body": f"try {len(tries)}" })

            if len(tries) < 3: raise Fault(Code.CONFLICT, reason="database.serialization")

            return len(tries)

        expect(await database.atomic(contended, attempts=3)).equals(3)
        expect(await notes().pluck("body")).equals(["try 3"])

        tries.clear()

        await test.rejects(database.atomic(contended, attempts=2), Code.CONFLICT, "database.serialization")

        expect(len(tries)).equals(2)

        async def refused () -> int:

            tries.append(1)

            raise error.conflict("taken")

        tries.clear()

        await test.rejects(database.atomic(refused, attempts=5), Code.CONFLICT, "taken")

        expect(len(tries)).equals(1)

        async with database.session() as session:

            deadlock = "DO $$ BEGIN RAISE EXCEPTION 'x' USING ERRCODE = '40P01'; END $$"
            serial   = "DO $$ BEGIN RAISE EXCEPTION 'x' USING ERRCODE = '40001'; END $$"

            await test.rejects(session.script(deadlock), Code.CONFLICT, "database.deadlock")
            await test.rejects(session.script(serial), Code.CONFLICT, "database.serialization")

    async def test_jobs_carry_the_request_context_into_workers ( self ) -> None:

        own  = Queue()
        seen: list[tuple[str | None, object]] = []

        async def observe () -> None:

            seen.append((context.request_id(), context.get("tenant")))

        async def reject () -> None:

            seen.append(("reject", None))

            raise error.validation({ "x": ["bad"] })

        own.setup(MemoryDriver(), ("default",), tries=5)

        with context.scope("request-00000077", tenant="acme", user=object()):

            job = await own.push(observe)

            expect(job.context).equals({ "tenant": "acme", "request_id": "request-00000077" })

        expect(await own.drain()).equals(1)
        expect(seen).equals([("request-00000077", "acme")])
        expect((context.request_id(), context.get("tenant"))).equals((None, None))

        await own.push(reject)

        expect((await own.drain(), len(own.failed()), seen[-1])).equals((1, 1, ("reject", None)))

    async def test_hung_jobs_time_out_with_an_unknown_outcome_and_retry ( self ) -> None:

        own   = Queue()
        calls: list[str] = []

        async def hang () -> None:

            calls.append("hang")

            await asyncio.sleep(5)

        own.setup(MemoryDriver(), ("default",), tries=2, backoff=0.0, timeout=0.05)

        job = await own.push(hang)

        expect((job.timeout, await own.drain(), calls)).equals((0.05, 2, ["hang", "hang"]))

        buried = own.failed()[0]

        expect((buried.job.id, buried.reason)).equals((job.id, "queue.timeout.hang"))
        expect((await own.enqueue(hang, timeout=0)).timeout).equals(0.0)

@dataclass(frozen=True, slots=True, kw_only=True)
class Label(Model):

    table      : ClassVar[str] = f"scratch_labels_{rand.hex(3)}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id   : Uuid
    name : str

@dataclass(frozen=True, slots=True, kw_only=True)
class Post(Model):

    table      : ClassVar[str] = f"scratch_posts_{rand.hex(3)}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False
    links      : ClassVar[str] = f"scratch_links_{rand.hex(3)}"
    relations  : ClassVar[Mapping[str, Relation]] = {
        "labels": belongs_to_many("Label", links, foreign="post_id", related_key="label_id"),
    }

    id    : Uuid
    title : str

@pytest.mark.anyio
class TestPivots:

    async def test_pivots_attach_detach_sync_and_toggle_without_duplicates ( self, app: App ) -> None:

        def labels ( table: Blueprint ) -> None:

            table.id()
            table.string("name", 40)

        def posts ( table: Blueprint ) -> None:

            table.id()
            table.string("title", 40)

        def links ( table: Blueprint ) -> None:

            table.foreign("post_id", Post.table, on_delete="cascade")
            table.foreign("label_id", Label.table, on_delete="cascade")
            table.timestamps()
            table.unique(["post_id", "label_id"])

        async with database.transaction() as session:

            await Schema(session).create(Label.table, labels)
            await Schema(session).create(Post.table, posts)
            await Schema(session).create(Post.links, links)

        try:

            post = await Query(Post, database).create({ "title": "hello" })
            red, blue, green = [await Query(Label, database).create({ "name": name }) for name in ("r", "b", "g")]
            pivot = Query(Post, database).pivot("labels")

            expect(await pivot.attach(post.id, red.id, blue.id, red.id)).equals(2)
            expect(await pivot.attach(post.id, red.id)).equals(0)
            expect((await pivot.has(post.id, red.id), await pivot.has(post.id, green.id))).equals((True, False))
            expect(await pivot.sync(post.id, [blue.id, green.id])).equals(
                { "attached": [str(green.id)], "detached": [str(red.id)] },
            )
            expect(await pivot.toggle(post.id, blue.id, red.id)).equals(
                { "attached": [str(red.id)], "detached": [str(blue.id)] },
            )
            expect(sorted(str(key) for key in await pivot.keys(post.id))).equals(sorted([str(green.id), str(red.id)]))

            loaded = await Query(Post, database).with_("labels").find(post.id)

            expect(sorted(label.name for label in (loaded.related["labels"] if loaded else []))).equals(["g", "r"])
            expect((await pivot.detach(post.id, green.id), await pivot.detach(post.id))).equals((1, 1))

            with test.fails(reason="Post.title"): Query(Post, database).pivot("title")

        finally:

            async with database.transaction() as session:

                for name in (Post.links, Post.table, Label.table): await Schema(session).drop(name)
