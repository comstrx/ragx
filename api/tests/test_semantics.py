from dataclasses import dataclass

from core.broadcast import Channels
from core.cache import Cache, MemoryStore
from core.event import Event, Events, LocalBus
from core.fast import Fast, Lru, Sliding, Ttl, Window
from core.health import Health
from core.llm import Sessions
from core.mail import LogMailer, Mail
from core.queue import MemoryDriver, Queue
from core.schedule import Schedule
from core.test import expect
import asyncio, pytest

@dataclass(frozen=True, slots=True)
class Pinged(Event):

    value: int

def noop () -> None:

    return None

@pytest.mark.anyio
class TestVerbs:

    async def test_clear_returns_what_it_removed_and_is_safe_to_repeat ( self ) -> None:

        cache  = Cache(MemoryStore())
        jobs   = Queue()
        fast   = Fast()
        lru: Lru[str, int] = Lru()
        ttl: Ttl[str, int] = Ttl()
        window = Window()
        slide  = Sliding()
        health = Health()
        plan   = Schedule()
        rooms  = Channels()
        talks  = Sessions()
        outbox = LogMailer()

        jobs.setup(MemoryDriver())

        await cache.set("a", 1)
        await cache.set("b", 2)
        await jobs.push(noop)

        fast.set("x", 1)
        lru.set("x", 1)
        ttl.set("x", 1)
        window.hit("k", 5, 60)
        slide.hit("k", 5, 60)
        health.register("db", lambda: True)
        plan.call(noop, "tick").every_minute()
        rooms.channel("room.{id}")
        talks.new("local")

        postman = Mail()

        postman.setup("app@x.test", mailer=outbox)

        await postman.to("a@x.test").about("hi").text("hello").send()

        cleared = [
            await cache.clear(), await jobs.clear(), fast.clear(), lru.clear(), ttl.clear(), window.clear(),
            slide.clear(), health.clear(), plan.clear(), rooms.clear(), talks.clear(), outbox.clear(),
        ]

        expect(cleared).equals([2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        expect([
            await cache.clear(), await jobs.clear(), fast.clear(), lru.clear(), ttl.clear(), window.clear(),
            slide.clear(), health.clear(), plan.clear(), rooms.clear(), talks.clear(), outbox.clear(),
        ]).each(lambda count: count == 0)

    async def test_forget_reports_whether_something_was_there ( self ) -> None:

        cache = Cache(MemoryStore())
        bus   = Events()
        plan  = Schedule()
        fast  = Fast()

        bus.setup(LocalBus())
        bus.listen(Pinged, lambda event: None)
        plan.call(noop, "tick").every_minute()
        fast.set("x", 1)

        await cache.set("a", 1)

        expect([await cache.forget("a"), bus.forget(Pinged), plan.forget("tick"), fast.forget("x")]).equals(
            [True, True, True, True],
        )
        expect([await cache.forget("a"), bus.forget(Pinged), plan.forget("tick"), fast.forget("x")]).equals(
            [False, False, False, False],
        )

    async def test_pause_holds_resume_releases_and_stop_close_are_idempotent ( self ) -> None:

        jobs  = Queue()
        bus   = Events()
        plan  = Schedule()
        heard: list[int] = []

        jobs.setup(MemoryDriver())
        bus.setup(LocalBus())
        bus.listen(Pinged, lambda event: heard.append(event.value))

        expect(jobs.start(2)).equals(2)
        expect((jobs.pause(), jobs.pause(), jobs.paused(), jobs.resume(), jobs.resume())).equals(
            (True, False, True, True, False),
        )
        expect((bus.pause(), bus.pause(), bus.paused())).equals((True, False, True))

        await bus.dispatch(Pinged(1))
        await bus.dispatch(Pinged(2))

        expect(heard).equals([])
        expect((await bus.resume(), heard, await bus.resume())).equals((2, [1, 2], 0))

        plan.call(noop, "tick").every_minute()
        plan.start(0.01)

        await asyncio.sleep(0.02)

        expect((plan.pause("tick"), plan.resume("tick"), plan.running())).equals((1, 1, True))
        expect((await jobs.stop(0.5), await jobs.stop(0.5), await plan.stop(0.5), await plan.stop(0.5))).equals(
            (2, 0, 1, 0),
        )
        expect((await bus.stop(0.5), await bus.stop(0.5))).equals((0, 0))

        await jobs.close()
        await jobs.close()

        expect((jobs.stats()["workers"], plan.running())).equals((0, False))
