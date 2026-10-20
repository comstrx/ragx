from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from core.database import Blueprint, Migrator, Model, Query, Schema, database
from core.error import Code
from core.http import App
from core.rand import Uuid, rand
from core.test import expect, test
import pytest

MIGRATION = """from core.database import Blueprint, Schema

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("title")
            table.foreign("parent_id", "{parent}")
            table.timestamps()

        await schema.create("{table}", define)

    async def down ( self, schema: Schema ) -> None:
        await schema.drop("{table}")
"""

def scratch ( label: str ) -> str:

    return f"scratch_{label}_{rand.hex(3)}"

def keyed ( table: Blueprint ) -> None:

    table.id()

@pytest.mark.anyio
class TestSchema:

    async def test_blueprints_create_alter_rename_and_drop_inside_one_transaction ( self, app: App ) -> None:

        name   = scratch("posts")
        other  = f"{name}_renamed"
        people = scratch("people")

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("title").unique()
            table.integer("views").default(0)
            table.boolean("published").default(False).index()
            table.json("meta").nullable()
            table.decimal("price")
            table.foreign("author_id", people)
            table.morphs("subject")
            table.enum("state", ("draft", "live"), kind=f"{name}_state")
            table.timestamps()
            table.soft_deletes()
            table.index(["published", "views"], include=["price"])
            table.gin("meta")
            table.fulltext(["title"])
            table.check("views >= 0", f"{name}_views_positive")

        def pivot ( table: Blueprint ) -> None:

            table.foreign("post_id", name, on_delete="cascade")
            table.foreign("author_id", people, on_delete="restrict")
            table.primary(["post_id", "author_id"])

        def alter ( table: Blueprint ) -> None:

            table.string("slug").nullable()
            table.unique(["slug"])
            table.drop_column("views")
            table.rename_column("title", "headline")
            table.drop_check(f"{name}_views_positive")
            table.drop_unique(f"{name}_title_key")
            table.rename_index(f"{name}_meta_index", f"{name}_feed_index")
            table.check("price >= 0", f"{name}_price_positive")

        def orphan ( table: Blueprint ) -> None:

            table.id()
            table.foreign("ghost_id", f"{name}_missing")

        with test.raises(RuntimeError, name):

            async with database.transaction() as session:

                schema = Schema(session)

                await schema.create(people, keyed)

                expect(await schema.has(name)).falsy()

                await schema.create(name, define)

                columns = set(await schema.columns(name))

                expect(await schema.has(name)).truthy()
                expect({
                    "id", "title", "views", "published", "meta", "price", "author_id", "subject_type", "subject_id",
                    "state", "created_at", "updated_at", "deleted_at",
                } <= columns).true()

                indexes = await schema.indexes(name)

                expect(indexes).contains(f"{name}_published_views_index")
                expect(indexes).contains(f"{name}_meta_index")
                expect(indexes).contains(f"{name}_title_fulltext")
                expect(indexes).contains(f"{name}_title_key")
                expect(await schema.constraints(name)).contains(f"{name}_views_positive")

                await schema.create(f"{name}_authors", pivot)

                expect(await schema.constraints(f"{name}_authors")).contains(f"{name}_authors_pkey")
                expect(await schema.constraints(f"{name}_authors")).contains(f"{name}_authors_author_id_fkey")

                await schema.table(name, alter)

                columns = set(await schema.columns(name))
                indexes = await schema.indexes(name)
                locks   = await schema.constraints(name)

                expect({"slug", "headline"} <= columns).true()
                expect({"views", "title"} & columns).falsy()
                expect(indexes).contains(f"{name}_feed_index")
                expect(indexes).lacks(f"{name}_meta_index")
                expect(indexes).lacks(f"{name}_published_views_index")
                expect(indexes).contains(f"{name}_slug_unique")
                expect(indexes).lacks(f"{name}_title_key")
                expect(locks).contains(f"{name}_price_positive")
                expect(locks).lacks(f"{name}_views_positive")

                await schema.rename(name, other)

                expect(await schema.has(other)).truthy()
                expect(await schema.has(name)).falsy()

                await schema.drop(f"{name}_authors")
                await schema.drop(other)

                expect(await schema.has(other)).falsy()

                raise RuntimeError(name)

        with test.fails(Code.INTERNAL, "database"):

            async with database.transaction() as session: await Schema(session).create(scratch("orphan"), orphan)

        async with database.transaction() as session: expect(await Schema(session).has(name)).falsy()

    async def test_migrator_applies_atomic_batches_and_rolls_them_back_in_reverse (
        self, app: App, tmp_path: Path,
    ) -> None:

        posts    = scratch("posts")
        comments = scratch("comments")
        people   = scratch("people")
        good     = tmp_path / "good"
        bad      = tmp_path / "bad"

        good.mkdir()
        bad.mkdir()
        (good / "0001_create_posts.py").write_text(MIGRATION.format(table=posts, parent=people))
        (good / "0002_create_comments.py").write_text(MIGRATION.format(table=comments, parent=posts))
        (good / "_draft.py").write_text("raise RuntimeError('never loaded')\n")
        (bad / "0001_create_posts.py").write_text(MIGRATION.format(table=posts, parent=people))
        (bad / "0002_create_broken.py").write_text(MIGRATION.format(table=scratch("broken"), parent="nowhere_at_all"))

        async with database.transaction() as session: await Schema(session).create(people, keyed)

        migrator = Migrator(database, good)
        before   = await migrator.status()

        expect(before["pending"]).equals(["0001_create_posts", "0002_create_comments"])
        expect([path.name for path in migrator.files()]).equals(["0001_create_posts.py", "0002_create_comments.py"])

        await test.rejects(Migrator(database, bad).apply(), Code.INTERNAL)

        async with database.transaction() as session: expect(await Schema(session).has(posts)).falsy()

        expect(await migrator.apply()).equals(["0001_create_posts", "0002_create_comments"])
        expect(await migrator.apply()).equals([])

        after = await migrator.status()

        async with database.transaction() as session:

            schema = Schema(session)

            expect(await schema.has(posts)).truthy()
            expect(await schema.has(comments)).truthy()
            expect(await schema.columns(comments)).contains("parent_id")

        expect(after["pending"]).equals([])
        expect(int(after["batch"]) >= 2).true()
        expect({"0001_create_posts", "0002_create_comments"} <= set(after["applied"])).true()
        expect(await migrator.rollback(1)).equals(["0002_create_comments", "0001_create_posts"])
        expect((await migrator.status())["pending"]).equals(["0001_create_posts", "0002_create_comments"])

        async with database.transaction() as session:

            schema = Schema(session)

            expect(await schema.has(posts)).falsy()
            expect(await schema.has(comments)).falsy()

            await schema.drop(people)

    async def test_migrators_keep_their_own_ledger_and_make_numbered_files ( self, app: App, tmp_path: Path ) -> None:

        tag    = rand.hex(3)
        people = scratch("people")

        async with database.transaction() as session: await Schema(session).create(people, keyed)

        ledger = f"scratch_ledger_{tag}"
        own    = Migrator(database, tmp_path / "own", ledger)

        (tmp_path / "own").mkdir()
        (tmp_path / "own" / "0001_create_things.py").write_text(
            MIGRATION.format(table=scratch("things"), parent=people),
        )

        try:

            expect(own.table).equals(ledger)
            expect(await own.apply()).equals(["0001_create_things"])
            expect(await own.apply()).equals([])
            expect(await own.fresh()).equals(["0001_create_things"])
            expect((await own.status())["batch"]).equals(1)
            expect(await own.reset()).equals(["0001_create_things"])
            expect((await own.status())["pending"]).equals(["0001_create_things"])
            expect(await own.reset()).equals([])

        finally:

            async with database.transaction() as session: await Schema(session).drop(ledger)

        migrator = Migrator(database, tmp_path / "made")
        made     = migrator.make("create widgets")

        expect(made.name).equals("0001_create_widgets.py")
        expect(made.read_text()).contains('schema.create("widgets"')
        expect(migrator.next_number()).equals(2)
        expect(callable(migrator.load(made).up)).truthy()
        expect(migrator.make("add color to widgets", table="widgets").name).equals("0002_add_color_to_widgets.py")

        async with database.transaction() as session: await Schema(session).drop(people)

    async def test_the_pool_fills_ahead_of_traffic ( self, app: App ) -> None:

        expect(await database.fill(4)).equals(4)
        expect(database.describe()["idle"]).above(3)
        expect(await database.fill(0)).equals(0)

    async def test_mapping_fields_bind_and_read_back_as_json_documents ( self, app: App ) -> None:

        @dataclass(frozen=True, slots=True, kw_only=True)
        class Card(Model):

            table      : ClassVar[str] = f"scratch_cards_{rand.hex(3)}"
            soft       : ClassVar[bool] = False
            timestamps : ClassVar[bool] = False

            id    : Uuid
            facts : Mapping[str, Any]
            extra : Mapping[str, Any] | None = None

        def define ( table: Blueprint ) -> None:

            table.id()
            table.json("facts")
            table.json("extra").nullable()

        async with database.transaction() as session: await Schema(session).create(Card.table, define)

        try:

            cards   = Query(Card, database)
            facts   = { "lang": "ar", "tags": ["vip"], "deep": { "n": 1 } }
            made    = await cards.create({ "facts": facts, "extra": { "ok": True } })
            nothing = await cards.create({ "facts": {}, "extra": None })
            found   = test.some(await cards.find(made.id))

            expect((found.facts, found.extra)).equals((facts, { "ok": True }))
            expect((await cards.find(nothing.id) or nothing).extra).none()
            expect(await cards.where("id", made.id).update({ "facts": { "lang": "en" } })).equals(1)
            expect((test.some(await cards.find(made.id))).facts).equals({ "lang": "en" })

        finally:

            async with database.transaction() as session: await Schema(session).drop(Card.table)
