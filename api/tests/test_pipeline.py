from dataclasses import dataclass

from core.broadcast import RedisDriver
from core.cache import Cache, RedisStore
from core.date import UTC, DateTime
from core.event import Event, Events, RabbitBus
from core.error import Code
from core.queue import Job, MemoryDriver, Queue, RabbitDriver, SyncDriver
from core.rand import rand
from core.schedule import Cron, Schedule
from core.socket import Connection, Frame, Socket
from core.test import expect, test
import asyncio, pytest

AMQP  = "amqp://guest:guest@127.0.0.1:5672/"
REDIS = "redis://127.0.0.1:6379/15"

@dataclass(frozen=True, slots=True)
class Shipped(Event):

    order : str

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

        expect(job.queue).equals("default")
        expect(late.available).above(job.available)
        expect(await own.size()).equals(2)
        expect(await own.drain()).equals(1)
        expect(calls).equals([7])
        expect(await own.size()).equals(1)

        await own.push(fragile, "flaky", queue="slow")

        for _ in range(3): await own.drain("slow")

        expect(calls.count("flaky")).equals(3)
        expect(buried).equals([])

        await own.push(fragile, "doomed", queue="slow", tries=2)

        for _ in range(2): await own.drain("slow")

        expect(calls.count("doomed")).equals(2)
        expect(buried).equals([("fragile", "RuntimeError")])
        expect(own.stats()["failures"]).equals(4)
        expect(own.stats()["processed"]).equals(2)
        expect(await own.clear()).equals(1)
        expect(await own.size()).equals(0)

        await test.rejects(own.push("nowhere:missing"), Code.INTERNAL, "queue.nowhere:missing")
        await test.rejects(own.push(sync_work, object()), Code.INTERNAL, "queue.payload")

        inline = Queue()

        inline.setup(SyncDriver())

        expect(inline.inline()).truthy()
        expect((await inline.push(sync_work, 9)).queue).equals("default")
        expect(calls[-1]).equals(9)
        expect(await inline.size()).equals(0)

@pytest.mark.anyio
class TestBrokers:

    async def test_rabbit_carries_jobs_with_receipts_delays_and_retries ( self ) -> None:

        tag    = rand.hex(3)
        own    = Queue()
        calls: list[object] = []
        driver = RabbitDriver(AMQP, exchange=f"jobs-{tag}", prefetch=4, quorum=False)

        async def work ( value: int ) -> None:

            calls.append(value)

            if value == 13: raise RuntimeError("unlucky")

        own.setup(driver, ("fast",), tries=2, backoff=0.0)

        try:

            expect(await own.clear("fast")).equals(0)
            expect(own.inline()).falsy()

            job = await own.push(work, 7, queue="fast")

            for _ in range(20):

                if await own.size("fast") == 1: break

                await asyncio.sleep(0.05)

            expect(job.queue).equals("fast")
            expect(await own.size("fast")).equals(1)

            pulled = await driver.pull("fast", 1.0)

            pulled = test.some(pulled)
            expect(pulled.id).equals(job.id)
            expect(pulled.args).equals((7,))
            expect(pulled.receipt).some()
            expect(await own.perform(pulled)).truthy()
            expect(calls).equals([7])
            expect(await own.size("fast")).equals(0)

            await own.push(work, 13, queue="fast")

            expect(await own.drain("fast")).equals(2)
            expect(calls).equals([7, 13, 13])
            expect(own.stats()["failures"]).equals(2)
            expect(await own.drain("fast")).equals(0)
            expect(await own.size("fast")).equals(0)
            expect(await driver.pull("fast", 0.2)).none()

            late = await own.push(work, 21, queue="fast", delay=0.4)

            expect(late.available).above(job.available)
            expect(await driver.pull("fast", 0.1)).none()

            await asyncio.sleep(0.6)

            expect(await own.drain("fast")).equals(1)
            expect(calls[-1]).equals(21)

        finally:

            await own.clear("fast")
            await own.close()

    async def test_rabbit_bus_moves_events_between_processes ( self ) -> None:

        tag      = rand.hex(3)
        sender   = Events()
        receiver = Events()
        heard: list[str] = []
        inbox    = f"test-{tag}.events"

        pipe     = RabbitBus(AMQP, exchange=f"events-{tag}", queue=inbox, prefetch=4)

        sender.setup(RabbitBus(AMQP, exchange=f"events-{tag}", queue=inbox, prefetch=4))
        receiver.setup(pipe)
        receiver.listen(Shipped, lambda event: heard.append(event.order))

        try:

            await pipe.inbox()

            receiver.start()

            expect(sender.bus().local).falsy()
            expect(await sender.dispatch(Shipped(f"o-{tag}"))).equals(0)

            for _ in range(50):

                if heard: break

                await asyncio.sleep(0.1)

            expect(heard).equals([f"o-{tag}"])

        finally:

            await receiver.stop()
            await sender.stop()

    async def test_redis_store_backs_the_cache_and_the_throttle ( self ) -> None:

        store = RedisStore(REDIS, prefix=f"unit-{rand.hex(3)}")
        cache = Cache(store)

        try:

            expect(await store.ping()).truthy()

            await cache.set("k", { "n": [1, 2] }, ttl=30)

            expect(await cache.get("k")).equals({ "n": [1, 2] })
            expect(await cache.has("k")).truthy()
            expect(0 < (await store.ttl("k") or 0) <= 30).true()
            expect(await store.ttl("missing")).none()
            expect(await cache.increment("n", 2, ttl=30)).equals(2)
            expect(await cache.increment("n")).equals(3)

            hits = [await cache.hit("bucket", 2, 30) for _ in range(3)]

            expect([hit.allowed for hit in hits]).equals([True, True, False])
            expect(0 < hits[2].reset <= 30).true()
            expect(await cache.forget("k")).truthy()
            expect(await cache.forget("k")).falsy()

            await cache.clear()

            expect(await cache.get("n")).none()

        finally:

            await cache.clear()
            await store.close()

    async def test_redis_fans_broadcasts_out_to_every_hub ( self ) -> None:

        topic  = f"unit-{rand.hex(3)}"
        left   = Socket()
        right  = Socket()
        first  = RedisDriver(left, REDIS, topic)
        second = RedisDriver(right, REDIS, topic)
        near   = left.attach(Connection("a", test.stub()))
        far    = right.attach(Connection("b", test.stub()))

        left.join(near, "news")
        right.join(far, "news")

        try:

            await first.start()
            await second.start()

            expect(first.publish("news", "headline", { "n": 1 }, None)).equals(1)

            for _ in range(100):

                if far.outbox.qsize(): break

                await asyncio.sleep(0.02)

            expect(Frame.decode(far.outbox.get_nowait())).equals(Frame("headline", "news", { "n": 1 }))
            expect(near.outbox.qsize()).equals(1)
            expect(second.describe()["relayed"]).equals(1)
            expect(first.describe()["relayed"]).equals(0)
            expect(first.origin()).differs(second.origin())
            expect(second.describe()["listening"]).truthy()

        finally:

            await first.stop()
            await second.stop()

    async def test_a_severed_redis_subscription_heals_and_keeps_relaying ( self ) -> None:

        topic  = f"unit-{rand.hex(3)}"
        left   = Socket()
        right  = Socket()
        sender = RedisDriver(left, REDIS, topic)
        far    = right.attach(Connection("b", test.stub()))

        right.join(far, "news")

        async def heard ( count: int ) -> int:

            for _ in range(150):

                if far.outbox.qsize() >= count: break

                expect(await sender.deliver("news", "tick", { "n": count }, None)).equals(0)

                await asyncio.sleep(0.02)

            return far.outbox.qsize()

        async with test.relay("127.0.0.1", 6379) as relay:

            hurt = RedisDriver(right, relay.url("redis", "/15"), topic)

            try:

                await hurt.start()

                expect(await heard(1)).equals(1)

                relay.sever()

                for _ in range(100):

                    if hurt.describe()["lost"]: break

                    await asyncio.sleep(0.02)

                expect(hurt.describe()).subset({ "lost": 1, "listening": True })
                expect(await heard(2)).above(1)

            finally:

                await hurt.stop()
                await sender.stop()

class TestSchedule:

    def test_cron_and_the_scheduler_know_when_tasks_are_due ( self ) -> None:

        table = Schedule()
        ran: list[str] = []
        cron  = Cron("*/15 2 * * 1-5")
        early = DateTime(2026, 10, 19, 0, 0, tzinfo=UTC)

        expect(cron.matches(DateTime(2026, 10, 19, 2, 30, tzinfo=UTC))).truthy()
        expect(cron.matches(DateTime(2026, 10, 18, 2, 30, tzinfo=UTC))).falsy()
        expect(cron.matches(DateTime(2026, 10, 19, 2, 31, tzinfo=UTC))).falsy()
        expect(Cron("@daily").matches(DateTime(2026, 1, 1, tzinfo=UTC))).truthy()
        expect(Cron("@hourly").matches(DateTime(2026, 1, 1, 0, 1, tzinfo=UTC))).falsy()
        expect(Cron("0 0 1 * 1").matches(DateTime(2026, 6, 1, tzinfo=UTC))).truthy()
        expect(Cron("0 0 1 * 1").matches(DateTime(2026, 6, 8, tzinfo=UTC))).truthy()

        with test.fails(Code.INTERNAL, "cron.range"): Cron("61 * * * *")
        with test.fails(Code.INTERNAL, "cron.fields"): Cron("* * *")

        quick = table.call(lambda: ran.append("quick"), "quick").every(60)
        night = table.call(lambda: ran.append("night"), "night").daily_at("03:00").timezone("Africa/Cairo")

        night.without_overlapping()

        expect([task.name for task in table.due(early)]).equals(["quick", "night"])
        expect(night.due(early)).truthy()
        expect(night.due(DateTime(2026, 10, 19, 1, 0, tzinfo=UTC))).falsy()

        night.running = True

        expect(night.due(early)).falsy()

        night.running = False
        night.started = early

        expect(night.due(early)).falsy()
        expect(quick.due(early)).truthy()
        expect(night.dump()["cron"]).equals("0 3 * * *")
        expect(table.find("quick")).is_(quick)

        with test.fails(Code.NOT_FOUND, "schedule.missing"): table.find("missing")
