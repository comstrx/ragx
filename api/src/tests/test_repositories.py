from core.database import Query, Seeds, database
from core.date import date
from core.error import Code
from core.http import App
from core.rand import rand
from core.parse import parse
from core.test import expect, test
from app.enums import Role as Roles, TokenKind
from app.models import Role, Token, User
from app.repositories import roles, tokens, users
from app.resources import user as resource
from database.seeders import seeders

class TestRepositories:

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

            expect(alice.id.version).equals(7)
            expect(alice.id).below(bob.id)
            expect(alice.created_at.tzinfo).some()
            expect(alice.deleted_at).none()
            expect(sorted(loaded.role_names())).equals(["admin", "client"])
            expect(loaded.has_role("admin")).truthy()
            expect(sorted(token.kind for token in loaded.related["tokens"])).equals(["access", "refresh"])
            owned = test.some(owned)
            expect(owned.related["owner"]).instance_of(User)
            expect(owned.related["owner"].id).equals(alice.id)
            expect({ user.id for user in member.related["users"] } >= { alice.id, bob.id }).true()
            expect(await scoped.count()).equals(2)
            expect(await scoped.exists()).truthy()
            expect(await scoped.order_by("name").pluck("name")).equals([f"Alice {tag}", f"Bob {tag}"])
            expect([user.name for user in await scoped.latest("name").get()]).equals([f"Bob {tag}", f"Alice {tag}"])
            alive = users.query().where_in("id", [alice.id, bob.id]).where_not_null("created_at")

            expect(await alive.count()).equals(2)
            expect(await users.query().where("created_at", ">", date.add(date.now(), days=1)).count()).equals(0)
            expect([user.name for user in rows]).equals([f"Alice {tag}"])
            expect(page).equals({ "page": 1, "limit": 1, "total": 2, "pages": 2 })
            expect(await users.query().where("id", alice.id).update({ "name": f"Alicia {tag}" })).equals(1)
            expect((await users.one(alice.id)).name).equals(f"Alicia {tag}")
            expect((await users.update(bob.id, { "name": f"Robert {tag}" })).name).equals(f"Robert {tag}")
            expect(await users.delete(bob.id)).truthy()
            expect(await users.find(bob.id)).none()
            expect(await scoped.count()).equals(1)
            expect(await users.query().with_trashed().find(bob.id)).some()
            expect([user.id for user in await scoped.only_trashed().get()]).equals([bob.id])
            expect(await users.restore(bob.id)).truthy()
            expect(await users.find(bob.id)).some()
            expect(await scoped.count()).equals(2)

            mail  = { "email": f"carol-{tag}@unit.test" }
            carol = await users.query().first_or_create(mail, { "name": "Carol", "password": None })
            same  = await users.query().first_or_create(mail, { "name": "Other" })
            moved = await users.query().update_or_create(mail, { "name": f"Carole {tag}" })
            pages = [len(batch) async for batch in scoped.order_by("name").chunk(2)]

            expect(carol.id == same.id == moved.id).true()
            expect(moved.name).equals(f"Carole {tag}")
            expect(pages).equals([2, 1])
            expect(await tokens.revoke(minted.id)).truthy()
            expect(await tokens.revoke(minted.id)).falsy()
            expect(await tokens.alive(f"fp-{tag}-1", TokenKind.REFRESH)).none()
            expect(await tokens.alive(f"fp-{tag}-2", TokenKind.ACCESS)).some()
            expect(await tokens.revoke_all(alice)).equals(1)
            expect(await tokens.query().where("owner_id", alice.id).force_delete()).equals(2)

            dumped = resource.one(loaded)

            expect(set(dumped)).equals({ "id", "name", "email", "created_at", "roles" })
            expect(dumped["id"]).equals(str(alice.id))
            expect(str(dumped["created_at"])).ends_with("Z")
            expect(sorted(map(str, parse.list(dumped["roles"])))).equals(["admin", "client"])

            await test.rejects(users.one(rand.uuid()), Code.NOT_FOUND, "users")

        finally:

            expect(await scoped.with_trashed().force_delete()).equals(3)

        expect(await users.query().where("id", alice.id).with_trashed().count()).equals(0)

    async def test_database_violations_become_typed_faults_and_the_pool_survives ( self, app: App ) -> None:

        tag   = rand.hex(4)
        email = f"dup-{tag}@unit.test"
        first = await users.create({ "name": "Dup", "email": email, "password": None })

        try:

            duplicate = users.create({ "name": "Dup", "email": email, "password": None })
            nameless  = users.create({ "name": None, "email": f"null-{tag}@unit.test", "password": None })
            conflict  = await test.rejects(duplicate, Code.CONFLICT, "users_email_alive")
            nulls     = await test.rejects(nameless, Code.VALIDATION, "name", field="name")

            await test.rejects(users.assign(first.id, rand.uuid()), Code.BAD_REQUEST, "role_user_role_id_fkey")

            with test.fails(Code.INTERNAL, "database"):

                async with database.session() as session: await session.script("select * from nowhere_at_all")

            expect((conflict.status, nulls.errors)).equals((409, { "name": [Code.VALIDATION.message()] }))
            expect(await database.ping()).truthy()
            expect(await users.find(first.id)).some()

        finally: await users.query().where("id", first.id).force_delete()

    async def test_seeders_are_idempotent_and_selectable ( self, app: App ) -> None:

        counts = (await roles.count(), await users.count())

        expect(await Seeds(database, seeders).run()).equals(["roles", "users"])
        expect(await Seeds(database, seeders).run(["roles"])).equals(["roles"])
        expect((await roles.count(), await users.count())).equals(counts)

        world = await users.find_by_email("world@ragx.test", "roles")

        world = test.some(world)
        expect(world.role_names()).equals([Roles.CLIENT.value])

    async def test_query_dsl_aggregates_upserts_cursors_and_renders_sql ( self, app: App ) -> None:

        tag   = rand.hex(4)
        base  = users.query().where_like("email", f"%-{tag}@q.test")
        names: list[str] = []
        mail  = { "name": f"A {tag}", "email": f"a-{tag}@q.test", "password": None }
        other = { "name": f"B {tag}", "email": f"b-{tag}@q.test", "password": None }

        expect(await users.query().insert([mail, other])).equals(2)
        expect(await users.query().insert([])).equals(0)

        try:

            ids = await base.order_by("name").pluck("id")

            expect(await base.count()).equals(2)
            expect(await base.max("name")).equals(f"B {tag}")
            expect(await base.min("name")).equals(f"A {tag}")
            expect(await base.order_by("name").value("name")).equals(f"A {tag}")
            expect(await base.where("name", "zzz").value("name")).none()
            by_mail = { mail["email"]: mail["name"], other["email"]: other["name"] }

            expect(await base.pluck("name", key="email")).equals(by_mail)
            expect(await base.where_either(("name", f"A {tag}"), ("name", "like", f"B %{tag}")).count()).equals(2)
            expect((await base.where_not("name", f"A {tag}").sole()).name).equals(f"B {tag}")
            expect(await base.where_in("name", [f"A {tag}"]).missing()).is_(False)
            expect(await base.where_not_in("name", [f"A {tag}", f"B {tag}"]).missing()).truthy()
            expect(await base.where_date("created_at", date.now().date()).count()).equals(2)
            soon = [date.add(date.now(), days=n) for n in (1, 2)]

            expect(await base.where_not_between("created_at", *soon).count()).equals(2)
            expect(await base.where_column("created_at", "<=", "updated_at").count()).equals(2)
            expect(await base.when(True, lambda q: q.where("name", f"A {tag}")).count()).equals(1)
            expect(await base.unless(True, lambda q: q.where("name", "zzz")).count()).equals(2)
            expect(await base.take(1).skip(1).order_by("name").pluck("name")).equals([f"B {tag}"])
            expect(await base.for_page(2, 1).order_by("name").pluck("name")).equals([f"B {tag}"])
            expect(base.distinct().to_sql()).contains("DISTINCT")
            expect(base.lock_for_update().to_sql()).contains("FOR UPDATE")
            expect(base.in_random_order().to_sql()).contains("random()")
            expect(base.shared_lock().to_sql()).contains("FOR SHARE")
            expect(base.dump()["filters"]).equals(1)
            expect(base.clone().state()).equals(base.state())
            expect(base.model()).is_(User)
            expect(base.columns()).contains("name")
            expect(base.reorder("name", "desc").state().orders).equals((("name", "desc"),))
            expect([user.name async for user in base.order_by("name").cursor(1)]).equals([f"A {tag}", f"B {tag}"])
            expect(await base.each(lambda user: names.append(user.name), 1)).equals(2)
            expect(sorted(names)).equals([f"A {tag}", f"B {tag}"])
            expect(len(await users.query().find_many(ids))).equals(2)
            expect(await users.query().find_many([])).equals([])
            expect(await base.touch()).equals(2)
            expect(base.with_("roles").without("roles").state().loads).equals(())
            expect(await base.order_by_desc("name").value("name")).equals(f"B {tag}")
            expect(await base.latest("name").value("name")).equals(f"B {tag}")

            await test.rejects(base.sole(), Code.CONFLICT, "users")

            with test.fails(Code.INTERNAL, "database.where"): base.where("name", "nope", 1, 2)
            with test.fails(Code.INTERNAL, "database.operator"): base.where("name", "~~", 1)
            with test.fails(Code.INTERNAL, "database.order"): base.order_by("name", "sideways")
            expect(await users.query().destroy(*ids)).equals(2)
            expect(await base.count()).equals(0)
            expect(await base.only_trashed().count()).equals(2)
            expect(await base.with_trashed().restore()).equals(2)
            expect(await base.count()).equals(2)
            expect(await users.query().destroy()).equals(0)

            label = f"role-{tag}"
            saved = await roles.query().upsert([{ "name": label, "label": "First" }], conflict=["name"])
            fresh = [{ "name": label, "label": "Second" }]
            again = await roles.query().upsert(fresh, conflict=["name"], update=["label"])
            role  = await roles.query().where("name", label).first_or_fail()

            expect(saved).equals(1)
            expect(again).equals(1)
            expect(role.label).equals("Second")
            expect(role).instance_of(Role)
            expect(await roles.query().where("name", label).force_delete()).equals(1)

        finally:

            expect(await base.with_trashed().force_delete()).equals(2)
