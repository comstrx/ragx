from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.database import Blueprint, Model, Query, Relation, Schema, belongs_to, database, morph_many, morph_to
from core.date import DateTime, date
from core.error import Code
from core.http import App
from core.rand import Uuid, rand
from core.test import expect, test
import pytest

SUFFIX = rand.hex(3)

@dataclass(frozen=True, slots=True, kw_only=True)
class Rank(Model):

    table : ClassVar[str] = f"scratch_ranks_{SUFFIX}"

    id         : Uuid
    name       : str
    created_at : DateTime
    updated_at : DateTime
    deleted_at : DateTime | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Person(Model):

    table     : ClassVar[str] = f"scratch_people_{SUFFIX}"
    relations : ClassVar[Mapping[str, Relation]] = {
        "rank"   : belongs_to("Rank", foreign="rank_id"),
        "badges" : morph_many("Badge", "owner"),
    }

    id         : Uuid
    rank_id    : Uuid
    name       : str
    email      : str | None = None
    tags       : list[str] = field(default_factory=list)
    profile    : Mapping[str, Any] = field(default_factory=dict)
    created_at : DateTime
    updated_at : DateTime
    deleted_at : DateTime | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Badge(Model):

    table     : ClassVar[str] = f"scratch_badges_{SUFFIX}"
    soft      : ClassVar[bool] = False
    relations : ClassVar[Mapping[str, Relation]] = { "owner": morph_to("owner") }

    id         : Uuid
    owner_type : str
    owner_id   : Uuid
    label      : str
    created_at : DateTime
    updated_at : DateTime

def ranks () -> Query[Rank]:

    return Query(Rank, database)

def people () -> Query[Person]:

    return Query(Person, database)

def badges () -> Query[Badge]:

    return Query(Badge, database)

@pytest.fixture
async def ranked ( app: App ) -> AsyncIterator[Rank]:

    def rank ( table: Blueprint ) -> None:

        table.id()
        table.string("name", 60).unique()
        table.timestamps()
        table.soft_deletes()

    def person ( table: Blueprint ) -> None:

        table.id()
        table.foreign("rank_id", Rank.table, on_delete="restrict")
        table.string("name", 120)
        table.string("email", 254).nullable()
        table.array("tags").default("{}")
        table.json("profile").default("{}")
        table.timestamps()
        table.soft_deletes()
        table.unique(["lower(email)"], name=f"{Person.table}_email", where="deleted_at IS NULL")

    def badge ( table: Blueprint ) -> None:

        table.id()
        table.morphs("owner")
        table.string("label", 60)
        table.timestamps()

    async with database.transaction() as session:

        for name, define in ((Rank.table, rank), (Person.table, person), (Badge.table, badge)):
            await Schema(session).create(name, define)

    try: yield await ranks().create({ "name": f"member-{SUFFIX}" })
    finally:

        async with database.transaction() as session:
            await Schema(session).drop_all(Badge.table, Person.table, Rank.table)

class TestOrm:

    async def test_relations_morphs_scopes_and_soft_deletes_round_trip ( self, ranked: Rank ) -> None:

        tag    = rand.hex(4)
        named  = { "rank_id": ranked.id }
        alice  = await people().create({ **named, "name": f"Alice {tag}", "email": f"alice-{tag}@unit.test" })
        bob    = await people().create({ **named, "name": f"Bob {tag}", "email": f"bob-{tag}@unit.test" })
        scoped = people().where_like("email", f"%-{tag}@unit.test")

        first = await badges().create({ "owner_type": Person.morph_name, "owner_id": alice.id, "label": "gold" })

        await badges().create({ "owner_type": Person.morph_name, "owner_id": alice.id, "label": "silver" })

        loaded     = await people().with_("rank", "badges").find_or_fail(alice.id)
        owned      = test.some(await badges().with_("owner").find(first.id))
        rows, page = await scoped.order_by("name").paginate(1, 1)

        expect(alice.id.version).equals(7)
        expect(alice.id).below(bob.id)
        expect(alice.created_at.tzinfo).some()
        expect((alice.deleted_at, alice.tags, alice.profile)).equals((None, [], {}))
        expect(loaded.related["rank"].name).equals(ranked.name)
        expect(sorted(badge.label for badge in loaded.related["badges"])).equals(["gold", "silver"])
        expect(owned.related["owner"]).instance_of(Person)
        expect(owned.related["owner"].id).equals(alice.id)
        expect((await scoped.count(), await scoped.exists())).equals((2, True))
        expect(await scoped.order_by("name").pluck("name")).equals([f"Alice {tag}", f"Bob {tag}"])
        expect([person.name for person in await scoped.latest("name").get()]).equals([f"Bob {tag}", f"Alice {tag}"])
        expect([person.name for person in rows]).equals([f"Alice {tag}"])
        expect(page).equals({ "page": 1, "limit": 1, "total": 2, "pages": 2 })
        expect(await people().where("id", alice.id).update({ "name": f"Alicia {tag}" })).equals(1)
        expect((await people().find_or_fail(alice.id)).name).equals(f"Alicia {tag}")
        expect(await people().where("id", bob.id).delete()).equals(1)
        expect(await people().find(bob.id)).none()
        expect(await people().with_trashed().find(bob.id)).some()
        expect([person.id for person in await scoped.only_trashed().get()]).equals([bob.id])
        expect(await people().where("id", bob.id).restore()).equals(1)
        expect(await scoped.count()).equals(2)

        mail  = { "email": f"carol-{tag}@unit.test" }
        carol = await people().first_or_create(mail, { "rank_id": ranked.id, "name": "Carol" })
        same  = await people().first_or_create(mail, { "name": "Other" })
        moved = await people().update_or_create(mail, { "name": f"Carole {tag}" })
        pages = [len(batch) async for batch in scoped.order_by("name").chunk(2)]

        expect(carol.id == same.id == moved.id).true()
        expect((moved.name, pages)).equals((f"Carole {tag}", [2, 1]))

        await test.rejects(people().find_or_fail(rand.uuid()), Code.NOT_FOUND, Person.table)

        expect(await badges().where("owner_id", alice.id).force_delete()).equals(2)
        expect(await scoped.with_trashed().force_delete()).equals(3)

    async def test_violations_become_typed_faults_and_the_pool_survives ( self, ranked: Rank ) -> None:

        tag   = rand.hex(4)
        email = f"dup-{tag}@unit.test"
        first = await people().create({ "rank_id": ranked.id, "name": "Dup", "email": email })

        duplicate = people().create({ "rank_id": ranked.id, "name": "Dup", "email": email.upper() })
        nameless  = people().create({ "rank_id": ranked.id, "name": None, "email": f"null-{tag}@unit.test" })
        orphan    = people().create({ "rank_id": rand.uuid(), "name": "Orphan" })
        conflict  = await test.rejects(duplicate, Code.CONFLICT, f"{Person.table}_email")
        nulls     = await test.rejects(nameless, Code.VALIDATION, "name", field="name")

        await test.rejects(orphan, Code.BAD_REQUEST, f"{Person.table}_rank_id_fkey")
        referenced = f"{Person.table}_rank_id_fkey"

        await test.rejects(ranks().where("id", ranked.id).force_delete(), Code.BAD_REQUEST, referenced)

        with test.fails(Code.INTERNAL, "database"):

            async with database.session() as session: await session.script("select * from nowhere_at_all")

        expect((conflict.status, nulls.errors)).equals((409, { "name": [Code.VALIDATION.message()] }))
        expect(await database.ping()).truthy()
        expect(await people().where("id", first.id).force_delete()).equals(1)

    async def test_the_query_dsl_aggregates_upserts_cursors_and_renders_sql ( self, ranked: Rank ) -> None:

        tag   = rand.hex(4)
        names : list[str] = []
        mail  = { "rank_id": ranked.id, "name": f"A {tag}", "email": f"a-{tag}@q.test" }
        other = { "rank_id": ranked.id, "name": f"B {tag}", "email": f"b-{tag}@q.test" }
        base  = people().where_like("email", f"%-{tag}@q.test")

        expect(await people().insert([mail, other])).equals(2)
        expect(await people().insert([])).equals(0)

        ids     = await base.order_by("name").pluck("id")
        by_mail = { mail["email"]: mail["name"], other["email"]: other["name"] }
        soon    = [date.add(date.now(), days=n) for n in (1, 2)]

        expect(await base.count()).equals(2)
        expect((await base.max("name"), await base.min("name"))).equals((f"B {tag}", f"A {tag}"))
        expect(await base.order_by("name").value("name")).equals(f"A {tag}")
        expect(await base.where("name", "zzz").value("name")).none()
        expect(await base.pluck("name", key="email")).equals(by_mail)
        expect(await base.where_either(("name", f"A {tag}"), ("name", "like", f"B %{tag}")).count()).equals(2)
        expect((await base.where_not("name", f"A {tag}").sole()).name).equals(f"B {tag}")
        expect(await base.where_in("name", [f"A {tag}"]).missing()).is_(False)
        expect(await base.where_not_in("name", [f"A {tag}", f"B {tag}"]).missing()).truthy()
        expect(await base.where_date("created_at", date.now().date()).count()).equals(2)
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
        expect(base.model()).is_(Person)
        expect(base.columns()).contains("name")
        expect(base.reorder("name", "desc").state().orders).equals((("name", "desc"),))
        expect([person.name async for person in base.order_by("name").cursor(1)]).equals([f"A {tag}", f"B {tag}"])
        expect(await base.each(lambda person: names.append(person.name), 1)).equals(2)
        expect(sorted(names)).equals([f"A {tag}", f"B {tag}"])
        expect(len(await people().find_many(ids))).equals(2)
        expect(await people().find_many([])).equals([])
        expect(await base.touch()).equals(2)
        expect(base.with_("rank").without("rank").state().loads).equals(())
        expect(await base.order_by_desc("name").value("name")).equals(f"B {tag}")

        await test.rejects(base.sole(), Code.CONFLICT, Person.table)

        with test.fails(Code.INTERNAL, "database.where"): base.where("name", "nope", 1, 2)
        with test.fails(Code.INTERNAL, "database.operator"): base.where("name", "~~", 1)
        with test.fails(Code.INTERNAL, "database.order"): base.order_by("name", "sideways")
        expect(await people().destroy(*ids)).equals(2)
        expect((await base.count(), await base.only_trashed().count())).equals((0, 2))
        expect(await base.with_trashed().restore()).equals(2)
        expect(await people().destroy()).equals(0)

        label = f"rank-{tag}"
        saved = await ranks().upsert([{ "name": label }], conflict=["name"])
        again = await ranks().upsert([{ "name": label }], conflict=["name"], update=["updated_at"])
        found = await ranks().where("name", label).first_or_fail()

        expect((saved, again)).equals((1, 1))
        expect(found).instance_of(Rank)
        expect(await ranks().where("name", label).force_delete()).equals(1)
        expect(await base.with_trashed().force_delete()).equals(2)
