from pathlib import Path
from uuid import UUID

from core.database import Blueprint, Migrator, Query, Schema, Seeds, database, sql
from core.date import date
from core.exceptions import Code, Fault
from core.http import App
from core.rand import rand
from core.value import value
from app.enums import Role as Roles, Table, TokenKind
from app.models import Token, User
from app.repositories import roles, tokens, users
from app.resources import user as resource
from database.seeders import seeders
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

@pytest.mark.anyio
class TestSchema:

    async def test_blueprints_create_alter_rename_and_drop_inside_one_transaction ( self, app: App ) -> None:

        name  = scratch("posts")
        other = f"{name}_renamed"

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("title").unique()
            table.integer("views").default(0)
            table.boolean("published").default(False).index()
            table.json("meta").nullable()
            table.decimal("price")
            table.foreign("author_id", Table.USERS)
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
            table.foreign("author_id", Table.USERS, on_delete="restrict")
            table.primary(["post_id", "author_id"])

        def alter ( table: Blueprint ) -> None:

            table.string("slug").nullable()
            table.unique(["slug"])
            table.drop_column("views")
            table.rename_column("title", "headline")
            table.drop_check(f"{name}_views_positive")
            table.drop_unique(f"{name}_title_key")
            table.rename_index(f"{name}_published_views_index", f"{name}_feed_index")
            table.check("price >= 0", f"{name}_price_positive")

        def orphan ( table: Blueprint ) -> None:

            table.id()
            table.foreign("ghost_id", f"{name}_missing")

        with pytest.raises(Fault):

            async with database.transaction() as session:

                schema = Schema(session)

                assert not await schema.has(name)

                await schema.create(name, define)

                columns = set(await schema.columns(name))

                assert await schema.has(name)
                assert {
                    "id", "title", "views", "published", "meta", "price", "author_id", "subject_type", "subject_id",
                    "state", "created_at", "updated_at", "deleted_at",
                } <= columns

                indexes = await schema.indexes(name)

                assert f"{name}_published_views_index" in indexes and f"{name}_meta_index" in indexes
                assert f"{name}_title_fulltext" in indexes and f"{name}_title_key" in indexes
                assert f"{name}_views_positive" in await schema.constraints(name)

                await schema.create(f"{name}_authors", pivot)

                assert f"{name}_authors_pkey" in await schema.constraints(f"{name}_authors")
                assert f"{name}_authors_author_id_fkey" in await schema.constraints(f"{name}_authors")

                await schema.table(name, alter)

                columns = set(await schema.columns(name))
                indexes = await schema.indexes(name)
                locks   = await schema.constraints(name)

                assert {"slug", "headline"} <= columns and not {"views", "title"} & columns
                assert f"{name}_feed_index" in indexes and f"{name}_published_views_index" not in indexes
                assert f"{name}_slug_unique" in indexes and f"{name}_title_key" not in indexes
                assert f"{name}_price_positive" in locks and f"{name}_views_positive" not in locks

                await schema.rename(name, other)

                assert await schema.has(other) and not await schema.has(name)

                await schema.drop(other)

                assert not await schema.has(other)

                raise RuntimeError(name)

        with pytest.raises(Fault) as refused:

            async with database.transaction() as session: await Schema(session).create(scratch("orphan"), orphan)

        assert refused.value.code == Code.INTERNAL

        async with database.transaction() as session: assert not await Schema(session).has(name)

    async def test_migrator_applies_atomic_batches_and_rolls_them_back_in_reverse (
        self, app: App, tmp_path: Path,
    ) -> None:

        posts    = scratch("posts")
        comments = scratch("comments")
        good     = tmp_path / "good"
        bad      = tmp_path / "bad"

        good.mkdir()
        bad.mkdir()
        (good / "0001_create_posts.py").write_text(MIGRATION.format(table=posts, parent=Table.USERS))
        (good / "0002_create_comments.py").write_text(MIGRATION.format(table=comments, parent=posts))
        (good / "_draft.py").write_text("raise RuntimeError('never loaded')\n")
        (bad / "0001_create_posts.py").write_text(MIGRATION.format(table=posts, parent=Table.USERS))
        (bad / "0002_create_broken.py").write_text(MIGRATION.format(table=scratch("broken"), parent="nowhere_at_all"))

        migrator = Migrator(database, good)
        before   = await migrator.status()

        assert before["pending"] == ["0001_create_posts", "0002_create_comments"]
        assert [path.name for path in migrator.files()] == ["0001_create_posts.py", "0002_create_comments.py"]

        with pytest.raises(Fault): await Migrator(database, bad).apply()

        async with database.transaction() as session: assert not await Schema(session).has(posts)

        assert await migrator.apply() == ["0001_create_posts", "0002_create_comments"]
        assert await migrator.apply() == []

        after = await migrator.status()

        async with database.transaction() as session:

            schema = Schema(session)

            assert await schema.has(posts) and await schema.has(comments)
            assert "parent_id" in await schema.columns(comments)

        assert after["pending"] == [] and int(after["batch"]) >= 2
        assert {"0001_create_posts", "0002_create_comments"} <= set(after["applied"])
        assert await migrator.rollback(1) == ["0002_create_comments", "0001_create_posts"]
        assert (await migrator.status())["pending"] == ["0001_create_posts", "0002_create_comments"]

        async with database.transaction() as session:

            schema = Schema(session)

            assert not await schema.has(posts) and not await schema.has(comments)

@pytest.mark.anyio
class TestOrm:

    async def test_models_relations_scopes_and_soft_deletes_round_trip ( self, app: App ) -> None:

        tag     = rand.hex(4)
        alice   = await users.create({ "name": f"Alice {tag}", "email": f"alice-{tag}@unit.test", "password": None })
        bob     = await users.create({ "name": f"Bob {tag}", "email": f"bob-{tag}@unit.test", "password": None })
        admin   = await roles.ensure(Roles.ADMIN.value, Roles.ADMIN.label())
        client  = await roles.ensure(Roles.CLIENT.value, Roles.CLIENT.label())
        expires = date.add(date.now(), days=1)
        scoped  = users.query().where_like("email", f"%-{tag}@unit.test")

        try:

            await users.assign(alice.id, admin.id)
            await users.assign(alice.id, client.id)
            await users.assign(alice.id, client.id)
            await users.assign(bob.id, client.id)

            minted = await tokens.remember(alice, TokenKind.REFRESH, f"fp-{tag}-1", expires)

            await tokens.remember(alice, TokenKind.ACCESS, f"fp-{tag}-2", expires)

            loaded = await users.one(alice.id, "roles", "tokens")
            owned  = await Query(Token, database).with_("owner").find(minted.id)
            member = await roles.one(client.id, "users")
            rows, page = await scoped.order_by("name").paginate(1, 1)

            assert isinstance(alice.id, UUID) and alice.id.version == 7 and alice.id < bob.id
            assert alice.created_at.tzinfo is not None and alice.deleted_at is None
            assert sorted(loaded.role_names()) == ["admin", "client"] and loaded.has_role("admin")
            assert sorted(token.kind for token in loaded.related["tokens"]) == ["access", "refresh"]
            assert owned is not None and isinstance(owned.related["owner"], User)
            assert owned.related["owner"].id == alice.id
            assert { user.id for user in member.related["users"] } >= { alice.id, bob.id }
            assert await scoped.count() == 2 and await scoped.exists()
            assert await scoped.order_by("name").pluck("name") == [f"Alice {tag}", f"Bob {tag}"]
            assert [user.name for user in await scoped.latest("name").get()] == [f"Bob {tag}", f"Alice {tag}"]
            assert await users.query().where_in("id", [alice.id, bob.id]).where_not_null("created_at").count() == 2
            assert await users.query().where("created_at", ">", date.add(date.now(), days=1)).count() == 0
            assert [user.name for user in rows] == [f"Alice {tag}"]
            assert page == { "page": 1, "limit": 1, "total": 2, "pages": 2 }
            assert await users.query().where("id", alice.id).update({ "name": f"Alicia {tag}" }) == 1
            assert (await users.one(alice.id)).name == f"Alicia {tag}"
            assert (await users.update(bob.id, { "name": f"Robert {tag}" })).name == f"Robert {tag}"
            assert await users.delete(bob.id) and await users.find(bob.id) is None and await scoped.count() == 1
            assert await users.query().with_trashed().find(bob.id) is not None
            assert [user.id for user in await scoped.only_trashed().get()] == [bob.id]
            assert await users.restore(bob.id) and await users.find(bob.id) is not None and await scoped.count() == 2

            mail  = { "email": f"carol-{tag}@unit.test" }
            carol = await users.query().first_or_create(mail, { "name": "Carol", "password": None })
            same  = await users.query().first_or_create(mail, { "name": "Other" })
            moved = await users.query().update_or_create(mail, { "name": f"Carole {tag}" })
            pages = [len(batch) async for batch in scoped.order_by("name").chunk(2)]

            assert carol.id == same.id == moved.id and moved.name == f"Carole {tag}" and pages == [2, 1]
            assert await tokens.revoke(minted.id) and not await tokens.revoke(minted.id)
            assert await tokens.alive(f"fp-{tag}-1", TokenKind.REFRESH) is None
            assert await tokens.alive(f"fp-{tag}-2", TokenKind.ACCESS) is not None
            assert await tokens.revoke_all(alice) == 1
            assert await tokens.query().where("owner_id", alice.id).force_delete() == 2

            dumped = resource.one(loaded)

            assert set(dumped) == { "id", "name", "email", "created_at", "roles" }
            assert dumped["id"] == str(alice.id) and str(dumped["created_at"]).endswith("Z")
            assert sorted(map(str, value.list(dumped["roles"]))) == ["admin", "client"]

            with pytest.raises(Fault) as missing: await users.one(rand.uuid())

            assert missing.value.code == Code.NOT_FOUND

        finally:

            assert await scoped.with_trashed().force_delete() == 3

        assert await users.query().where("id", alice.id).with_trashed().count() == 0

    async def test_database_violations_become_typed_faults_and_the_pool_survives ( self, app: App ) -> None:

        tag   = rand.hex(4)
        email = f"dup-{tag}@unit.test"
        first = await users.create({ "name": "Dup", "email": email, "password": None })

        try:

            with pytest.raises(Fault) as conflict:
                await users.create({ "name": "Dup", "email": email, "password": None })
            with pytest.raises(Fault) as reference: await users.assign(first.id, rand.uuid())
            with pytest.raises(Fault) as nulls:
                await users.create({ "name": None, "email": f"null-{tag}@unit.test", "password": None })
            with pytest.raises(Fault) as unknown: await database.fetch(sql("select * from nowhere_at_all"))

            assert (conflict.value.code, conflict.value.status) == (Code.CONFLICT, 409)
            assert (reference.value.code, nulls.value.code) == (Code.BAD_REQUEST, Code.VALIDATION)
            assert unknown.value.code == Code.INTERNAL
            assert nulls.value.errors == { "name": [Code.VALIDATION.message()] }
            assert await database.ping() and await users.find(first.id) is not None

        finally: await users.query().where("id", first.id).force_delete()

    async def test_seeders_are_idempotent_and_selectable ( self, app: App ) -> None:

        counts = (await roles.count(), await users.count())

        assert await Seeds(database, seeders).run() == ["roles", "users"]
        assert await Seeds(database, seeders).run(["roles"]) == ["roles"]
        assert (await roles.count(), await users.count()) == counts

        world = await users.find_by_email("world@ragx.test", "roles")

        assert world is not None and world.role_names() == [Roles.CLIENT.value]
