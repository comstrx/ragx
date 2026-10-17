from dataclasses import dataclass

from core.date import UTC, DateTime
from core.event import events
from core.exceptions import Fault
from core.http import App
from core.mail import MemoryTransport
from core.queue import Job, MemoryDriver, Queue, Queued, SyncDriver, queue
from core.rand import rand
from core.schedule import Cron, Schedule
from app.enums import TokenKind
from app.events import UserRegistered
from app.jobs import PurgeTokens
from app.mails import WelcomeMail
from app.repositories import tokens, users
from app.utils.bases import BaseEvent, BaseJob, BaseListener
from routes import schedule as timetable
import pytest

voices: list[str] = []
counted: list[tuple[int, int]] = []
OLD = DateTime(2020, 1, 1, tzinfo=UTC)

@dataclass(frozen=True, slots=True)
class Pinged(BaseEvent):

    tag : str

class Loud(BaseListener, Queued):

    async def handle ( self, event: Pinged ) -> None:
        voices.append(f"loud:{event.tag}")

class Quiet(BaseListener):

    async def handle ( self, event: Pinged ) -> None:
        voices.append(f"quiet:{event.tag}")

class Counting(BaseJob):

    async def handle ( self ) -> None:
        counted.append((self.args[0], self.kwargs.get("step", 1)))

class Count(Counting, Queued):

    queue = "maintenance"

class CountNow(Counting):

    pass

def short ( job: Job ) -> str:
    return job.name.rsplit(".", 1)[-1]

@pytest.mark.anyio
class TestPipeline:

    async def test_queue_runs_retries_and_buries_jobs_in_any_driver ( self ) -> None:

        own    = Queue()
        calls: list[object] = []
        buried: list[tuple[str, str]] = []

        async def fragile ( label: str ) -> None:

            calls.append(label)

            if calls.count(label) < 3: raise RuntimeError(label)

        def sync_work ( value: int ) -> None:
            calls.append(value)

        own.setup(MemoryDriver(), ("default", "slow"), tries=3, backoff=0.0)
        own.on_failure(lambda job, error: buried.append((short(job), type(error).__name__)))

        task = own.task(sync_work)
        job  = await task.later(7)
        late = await task.after(0.05, 8)

        assert isinstance(job, Job) and job.queue == "default" and late.available > job.available
        assert await own.size() == 2 and await own.drain() == 1 and calls == [7] and await own.size() == 1

        await own.push(fragile, "flaky", queue="slow")

        for _ in range(3): await own.drain("slow")

        assert calls.count("flaky") == 3 and buried == []

        await own.push(fragile, "doomed", queue="slow", tries=2)

        for _ in range(2): await own.drain("slow")

        assert calls.count("doomed") == 2 and buried == [("fragile", "RuntimeError")]
        assert own.stats()["failures"] == 4 and own.stats()["processed"] == 2
        assert await own.clear() == 1 and await own.size() == 0

        with pytest.raises(Fault): await own.push("nowhere:missing")
        with pytest.raises(TypeError): await own.push(sync_work, object())

        inline = Queue()

        inline.setup(SyncDriver())

        assert inline.inline() and await inline.push(sync_work, 9) and calls[-1] == 9 and await inline.size() == 0

    async def test_events_jobs_and_mails_queue_or_run_inline_by_inheritance (
        self, app: App, outbox: MemoryTransport,
    ) -> None:

        tag  = rand.hex(3)
        user = await users.create({ "name": f"Job {tag}", "email": f"job-{tag}@unit.test", "password": None })

        events.listen(Pinged, Loud, Quiet)

        try:

            await queue.clear()
            await queue.clear("maintenance")

            waited = events.until(Pinged)
            heard  = await Pinged(tag).dispatch()

            assert heard == 2 and voices == [f"quiet:{tag}"] and waited.done() and waited.result().tag == tag
            assert await queue.drain() == 1 and voices == [f"quiet:{tag}", f"loud:{tag}"]
            assert await Count.dispatch(1, step=2) is not None and counted == []
            assert await queue.size("maintenance") == 1 and await queue.drain("maintenance") == 1
            assert counted == [(1, 2)]
            assert await CountNow.dispatch(3) is None and counted == [(1, 2), (3, 1)]

            outbox.clear()

            sent = await WelcomeMail(name="Queued", app="RagX").to(f"q-{tag}@unit.test").send()

            assert sent is None and outbox.last() is None and await queue.drain() == 1

            queued = outbox.last()

            assert queued is not None and queued.subject == "Welcome to RagX, Queued"

            now = await WelcomeMail(name="Direct", app="RagX").to(f"d-{tag}@unit.test").send_now()

            assert now.subject == "Welcome to RagX, Direct" and outbox.last() is now

            await tokens.remember(user, TokenKind.ACCESS, f"old-{tag}", OLD)

            assert await PurgeTokens.dispatch() is not None and await queue.drain("maintenance") == 1
            assert await tokens.query().where("hash", f"old-{tag}").count() == 0

            await UserRegistered(str(user.id), user.name, user.email).dispatch()

            assert await queue.drain() == 1

            welcome = outbox.last()

            assert welcome is not None and welcome.to == (user.email,)

        finally:

            events.forget(Pinged)

            await users.query().where("id", user.id).force_delete()

class TestSchedule:

    def test_cron_and_the_scheduler_know_when_tasks_are_due ( self ) -> None:

        table = Schedule()
        ran: list[str] = []
        cron  = Cron("*/15 2 * * 1-5")
        early = DateTime(2026, 10, 19, 0, 0, tzinfo=UTC)

        assert cron.matches(DateTime(2026, 10, 19, 2, 30, tzinfo=UTC))
        assert not cron.matches(DateTime(2026, 10, 18, 2, 30, tzinfo=UTC))
        assert not cron.matches(DateTime(2026, 10, 19, 2, 31, tzinfo=UTC))
        assert Cron("@daily").matches(DateTime(2026, 1, 1, tzinfo=UTC))
        assert not Cron("@hourly").matches(DateTime(2026, 1, 1, 0, 1, tzinfo=UTC))
        assert Cron("0 0 1 * 1").matches(DateTime(2026, 6, 1, tzinfo=UTC))
        assert Cron("0 0 1 * 1").matches(DateTime(2026, 6, 8, tzinfo=UTC))

        with pytest.raises(Fault): Cron("61 * * * *")
        with pytest.raises(Fault): Cron("* * *")

        quick = table.call(lambda: ran.append("quick"), "quick").every(60)
        night = table.call(lambda: ran.append("night"), "night").daily_at("03:00").timezone("Africa/Cairo")

        night.without_overlapping()

        assert [task.name for task in table.due(early)] == ["quick", "night"]
        assert night.due(early) and not night.due(DateTime(2026, 10, 19, 1, 0, tzinfo=UTC))

        night.running = True

        assert not night.due(early)

        night.running = False
        night.started = early

        assert not night.due(early) and quick.due(early) and night.dump()["cron"] == "0 3 * * *"
        assert [task.name for task in timetable.tasks] == ["tokens.purge"] and timetable.tasks[0].exclusive
        assert table.find("quick") is quick

        with pytest.raises(Fault): table.find("missing")
