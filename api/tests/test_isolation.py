from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import ClassVar

from core.context import context
from core.database import Blueprint, Model, Query, Schema, database
from core.error import Code
from core.http import App
from core.queue import MemoryDriver, Queue
from core.rand import Uuid, rand
from core.test import expect, test
import asyncio, pytest

@dataclass(frozen=True, slots=True, kw_only=True)
class Memo(Model):

    table      : ClassVar[str] = f"scratch_memos_{rand.hex(3)}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id        : Uuid
    tenant_id : Uuid
    body      : str

def memos () -> Query[Memo]:

    return Query(Memo, database)

@contextmanager
def tenant ( key: Uuid ) -> Iterator[Mapping[str, str]]:

    with database.bound({ "app.tenant": str(key) }) as bound: yield bound

@pytest.fixture
async def table ( app: App ) -> AsyncIterator[str]:

    def define ( blueprint: Blueprint ) -> None:

        blueprint.id()
        blueprint.uuid("tenant_id")
        blueprint.string("body", 80)
        blueprint.index(["tenant_id"])
        blueprint.isolated()

    async with database.transaction() as session: await Schema(session).create(Memo.table, define)

    try: yield Memo.table
    finally:

        async with database.transaction() as session: await Schema(session).drop(Memo.table)

class TestIsolation:

    async def test_rows_live_behind_a_forced_policy_the_owning_role_cannot_skip ( self, table: str ) -> None:

        first, second = rand.uuid(), rand.uuid()

        async with database.transaction() as session: expect(await Schema(session).isolated(table)).true()

        await test.rejects(memos().create({ "tenant_id": first, "body": "x" }), Code.FORBIDDEN, "database.privilege")

        with tenant(first):

            await memos().create({ "tenant_id": first, "body": "a1" })
            await memos().create({ "tenant_id": first, "body": "a2" })
            await test.rejects(
                memos().create({ "tenant_id": second, "body": "smuggled" }), Code.FORBIDDEN, "database.privilege",
            )

        with tenant(second): theirs = await memos().create({ "tenant_id": second, "body": "b1" })

        with tenant(first):

            expect(await memos().count()).equals(2)
            expect(await memos().where("id", theirs.id).update({ "body": "stolen" })).equals(0)
            expect(await memos().where("id", theirs.id).delete()).equals(0)

            async with database.transaction(): expect(sorted(await memos().pluck("body"))).equals(["a1", "a2"])

        with tenant(second): expect([memo.body for memo in await memos().get()]).equals(["b1"])

        expect(await memos().count()).equals(0)

        async with database.transaction() as session:

            await Schema(session).share(table)

            expect(await Schema(session).isolated(table)).false()

        expect(await memos().count()).equals(3)

    async def test_a_binding_lives_for_one_transaction_and_never_opens_inside_one ( self, table: str ) -> None:

        key = rand.uuid()

        with tenant(key): await memos().create({ "tenant_id": key, "body": "kept" })

        expect(await memos().count()).equals(0)

        async with database.transaction():

            with test.fails(Code.INTERNAL, "database.bound.open"), tenant(key): pass

        with test.fails(Code.INTERNAL, "database.bound"), database.bound({ "tenant": str(key) }): pass

        with tenant(key):

            async with database.transaction(), database.transaction(): expect(await memos().count()).equals(1)

            with database.bound({ "app.region": "eu" }) as bound: expect(dict(bound)).equals(
                { "app.tenant": str(key), "app.region": "eu" },
            )

        expect(await memos().count()).equals(0)

    async def test_concurrent_tenants_on_one_pool_never_see_each_other ( self, table: str ) -> None:

        keys = [rand.uuid() for _ in range(4)]

        for index, key in enumerate(keys):

            with tenant(key):

                await memos().insert([
                    { "id": rand.uuid(), "tenant_id": key, "body": f"{index}-{count}" } for count in range(index + 1)
                ])

        async def seen ( key: Uuid ) -> tuple[set[Uuid], int]:

            with tenant(key):

                async with database.transaction():

                    await asyncio.sleep(0)

                    found = await memos().get()

                return { memo.tenant_id for memo in found }, await memos().count()

        found = await asyncio.gather(*(seen(keys[turn % 4]) for turn in range(40)))

        expect(found).equals([({ keys[turn % 4] }, turn % 4 + 1) for turn in range(40)])
        expect(await memos().count()).equals(0)

    async def test_a_followed_context_slot_binds_requests_and_the_jobs_they_dispatch ( self, table: str ) -> None:

        key  = rand.uuid()
        jobs = Queue()
        seen : list[int] = []

        async def tally () -> None:

            seen.append(await memos().count())

        jobs.setup(MemoryDriver())
        database.follow("app.tenant", "scratch_tenant")

        try:

            with context.bind(scratch_tenant=str(key)):

                await memos().create({ "tenant_id": key, "body": "carried" })

                expect(await memos().count()).equals(1)

                await jobs.push(tally)

            expect((await memos().count(), await jobs.drain(), seen)).equals((0, 1, [1]))

        finally: database.follow("app.tenant", None)

        expect(database.describe()["follows"]).equals({})
