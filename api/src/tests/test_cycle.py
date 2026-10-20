from dataclasses import dataclass
from typing import ClassVar, override

from core.database import Blueprint, Model, Schema, database
from core.date import DateTime
from core.error import Code
from core.event import events
from core.http import App
from core.mail import LogMailer
from core.queue import Queued, queue
from core.rand import Uuid, rand
from core.test import expect, test
from app.utils.cycle import Controller, Event, Job, Listener, Mail, Repository, Resource

SUFFIX = rand.hex(3)
heard: list[str] = []
done : list[int] = []

@dataclass(frozen=True, slots=True, kw_only=True)
class Item(Model):

    table : ClassVar[str] = f"scratch_items_{SUFFIX}"

    id         : Uuid
    name       : str
    created_at : DateTime
    updated_at : DateTime
    deleted_at : DateTime | None = None

class Items(Repository[Item]):

    model = Item

class Shown(Resource[Item]):

    fields: tuple[str, ...] = ("id", "name", "created_at")

    @override
    def additional ( self, model: Item ) -> dict[str, object]:

        return { "upper": model.name.upper() }

@dataclass(frozen=True, slots=True)
class Pinged(Event):

    tag : str

class Loud(Listener, Queued):

    @override
    async def handle ( self, event: Pinged ) -> None:

        heard.append(f"loud:{event.tag}")

class Quiet(Listener):

    @override
    async def handle ( self, event: Pinged ) -> None:

        heard.append(f"quiet:{event.tag}")

class Count(Job, Queued):

    queue = "maintenance"

    @override
    async def handle ( self ) -> None:

        done.append(int(str(self.args[0])))

class Note(Mail, Queued):

    subject = "Note for {name}"
    html    = "layouts/mail.html"

class TestCycle:

    async def test_the_bases_dispatch_queue_mail_page_and_render_without_any_business (
        self, app: App, outbox: LogMailer,
    ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("name", 60)
            table.timestamps()
            table.soft_deletes()

        async with database.transaction() as session: await Schema(session).create(Item.table, define)

        events.listen(Pinged, Loud, Quiet)

        try:

            items = Items()
            made  = await items.create({ "name": "first" })
            other = await items.create({ "name": "second" })
            rows, page = await items.all(1, 1)

            expect((await items.one(made.id)).name).equals("first")
            expect((await items.update(other.id, { "name": "moved" })).name).equals("moved")
            expect((await items.delete(made.id), await items.find(made.id), await items.restore(made.id))).equals(
                (True, None, True),
            )
            expect((len(rows), page["total"], await items.count())).equals((1, 2, 2))

            await test.rejects(items.one("not-an-id"), Code.BAD_REQUEST, "id")

            shown = Shown().one(made)

            expect(set(shown)).equals({ "id", "name", "created_at", "upper" })
            expect((shown["id"], shown["upper"], str(shown["created_at"])[-1])).equals((str(made.id), "FIRST", "Z"))

            tag = rand.hex(3)

            expect(await Pinged(tag).dispatch()).equals(2)
            expect(heard[-1:]).equals([f"quiet:{tag}"])
            expect(await queue.drain()).equals(1)
            expect(heard[-2:]).equals([f"quiet:{tag}", f"loud:{tag}"])
            expect(await Count.dispatch(7)).some()
            expect((done, await queue.drain("maintenance"), done)).equals(([7], 1, [7]))

            outbox.clear()

            expect(await Note(name="Ann").to("ann@unit.test").send()).none()
            expect(await queue.drain()).equals(1)
            expect(test.some(outbox.last()).subject).equals("Note for Ann")

            await test.rejects(Note(name="x").send_now(), Code.BAD_REQUEST, "mail.to")

            replies = Controller()

            codes   = [replies.ok({}), replies.created({}), replies.no_content(), replies.page([1], 3, 1, 1)]

            expect([reply.status_code for reply in codes]).equals([200, 201, 204, 200])

        finally:

            events.forget(Pinged)

            async with database.transaction() as session: await Schema(session).drop(Item.table)
