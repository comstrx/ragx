from dataclasses import dataclass
from typing import override

from core.date import UTC, DateTime
from core.event import events
from core.http import App
from core.mail import LogMailer
from core.queue import Queued, queue
from core.rand import rand
from core.test import expect, test
from app.enums import TokenKind
from app.events import UserRegistered
from app.jobs import PurgeTokens
from app.mails import WelcomeMail
from app.repositories import tokens, users
from app.utils import cycle
from routes import schedule as timetable

voices: list[str] = []
counted: list[tuple[int, int]] = []
OLD = DateTime(2020, 1, 1, tzinfo=UTC)

@dataclass(frozen=True, slots=True)
class Pinged(cycle.Event):

    tag : str

class Loud(cycle.Listener, Queued):

    @override
    async def handle ( self, event: Pinged ) -> None:

        voices.append(f"loud:{event.tag}")

class Quiet(cycle.Listener):

    @override
    async def handle ( self, event: Pinged ) -> None:

        voices.append(f"quiet:{event.tag}")

class Counting(cycle.Job):

    @override
    async def handle ( self ) -> None:

        counted.append((self.args[0], self.kwargs.get("step", 1)))

class Count(Counting, Queued):

    queue = "maintenance"

class CountNow(Counting):

    pass

class TestCycle:

    async def test_events_jobs_and_mails_queue_or_run_inline_by_inheritance (
        self, app: App, outbox: LogMailer,
    ) -> None:

        tag  = rand.hex(3)
        user = await users.create({ "name": f"Job {tag}", "email": f"job-{tag}@unit.test", "password": None })

        events.listen(Pinged, Loud, Quiet)

        try:

            await queue.clear()
            await queue.clear("maintenance")

            waited = events.until(Pinged)
            heard  = await Pinged(tag).dispatch()

            expect(heard).equals(2)
            expect(voices).equals([f"quiet:{tag}"])
            expect(waited.done()).truthy()
            expect(waited.result().tag).equals(tag)
            expect(await queue.drain()).equals(1)
            expect(voices).equals([f"quiet:{tag}", f"loud:{tag}"])
            expect(await Count.dispatch(1, step=2)).some()
            expect(counted).equals([])
            expect(await queue.size("maintenance")).equals(1)
            expect(await queue.drain("maintenance")).equals(1)
            expect(counted).equals([(1, 2)])
            expect(await CountNow.dispatch(3)).none()
            expect(counted).equals([(1, 2), (3, 1)])

            outbox.clear()

            sent = await WelcomeMail(name="Queued", app="RagX").to(f"q-{tag}@unit.test").send()

            expect(sent).none()
            expect(outbox.last()).none()
            expect(await queue.drain()).equals(1)

            queued = outbox.last()

            queued = test.some(queued)
            expect(queued.subject).equals("Welcome to RagX, Queued")

            now = await WelcomeMail(name="Direct", app="RagX").to(f"d-{tag}@unit.test").send_now()

            expect(now.subject).equals("Welcome to RagX, Direct")
            expect(outbox.last()).is_(now)

            await tokens.remember(user, TokenKind.ACCESS, f"old-{tag}", OLD)

            expect(await PurgeTokens.dispatch()).some()
            expect(await queue.drain("maintenance")).equals(1)
            expect(await tokens.query().where("hash", f"old-{tag}").count()).equals(0)

            await UserRegistered(str(user.id), user.name, user.email).dispatch()

            expect(await queue.drain()).equals(1)

            welcome = outbox.last()

            welcome = test.some(welcome)
            expect(welcome.recipients).equals((user.email,))

        finally:

            events.forget(Pinged)

            await users.query().where("id", user.id).force_delete()

    def test_the_timetable_purges_tokens_on_one_server ( self ) -> None:

        expect([task.name for task in timetable.tasks]).equals(["tokens.purge"])
        expect(timetable.tasks[0].exclusive).truthy()
