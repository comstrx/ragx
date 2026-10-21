from core.broker import Parcel, RabbitBroker
from core.cache import Cache, RedisStore
from core.config import env
from core.database import Database, Schema as Tables, adapters, database
from core.error import Code, Fault
from core.http import App
from core.queue import Queue, RabbitDriver
from core.rand import rand
from core.test import expect, test
from core.thread import thread
import asyncio

AMQP = "amqp://guest:guest@127.0.0.1:5672/"
KILL = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
    "WHERE usename = current_user AND datname = current_database() AND pid <> pg_backend_pid()"
)

class TestRecovery:

    async def test_the_pool_heals_after_the_database_terminates_its_connections ( self, app: App ) -> None:

        adapter = adapters.resolve(env.text("DB_DRIVER", "postgresql"))
        target  = adapter.url(
            env.text("DB_HOST", "127.0.0.1"), env.int("DB_PORT", 5432), env.text("DB_DATABASE"),
            env.text("DB_USERNAME", "ragx"), env.text("DB_PASSWORD"),
        )
        options = adapter.options(env.text("DB_SSLMODE", "disable"), "public", "recovery")
        watched = Database()
        killer  = Database()

        await watched.connect(adapter, target, 3, 3, 5.0, options, idle=0.0)
        await killer.connect(adapter, target, 1, 1, 5.0, options)
        await watched.fill(3)
        await database.fill(4)

        try:
            async with killer.transaction() as session: await session.script(KILL)
        finally: await killer.close()

        healed = [await watched.ping() for _ in range(6)]
        pings  = [await database.ping() for _ in range(6)]
        tables = []

        for _ in range(6):

            async with database.session() as session: tables.append("outbox" in await Tables(session).tables())

        await watched.close()

        expect((healed, pings[1:], pings.count(False) <= 1, tables)).equals(([True] * 6, [True] * 5, True, [True] * 6))

    async def test_a_redis_outage_is_a_fault_locks_fail_closed_throttles_degrade_and_the_store_heals ( self ) -> None:

        async with test.relay("127.0.0.1", 6379) as relay:

            store = RedisStore(relay.url("redis", "/15"), f"unit-{rand.hex(3)}", wait=0.5)
            cache = Cache(store)

            try:

                await cache.set("kept", { "n": 1 }, ttl=60)

                await relay.down()

                await test.rejects(cache.get("kept"), Code.UNAVAILABLE, "cache")
                await test.rejects(cache.lock("job", 5).acquire(), Code.UNAVAILABLE, "cache")

                hits = [await cache.hit("throttle:login:a", 2, 60) for _ in range(3)]

                expect([hit.allowed for hit in hits]).equals([True, True, False])
                expect(cache.stats()["shed"]).equals(3)

                await relay.up()

                expect(await cache.get("kept")).equals({ "n": 1 })
                expect((await cache.hit("throttle:login:b", 2, 60)).allowed).truthy()
                expect(cache.stats()["shed"]).equals(3)

            finally: await store.close()

    async def test_a_rabbit_outage_refuses_publishing_and_the_robust_connection_returns ( self ) -> None:

        async with test.relay("127.0.0.1", 5672) as relay:

            target = relay.url("amqp", "/?reconnect_interval=0.2", "guest:guest")
            broker = RabbitBroker(target, f"unit-{rand.hex(3)}", 4)
            queue  = f"work-{rand.hex(3)}"

            async def published () -> bool:

                try: await broker.publish(queue, b"after")
                except Fault: return False

                return True

            try:

                await broker.publish(queue, b"before")

                await relay.down()

                await test.rejects(broker.publish(queue, b"lost"), Code.UNAVAILABLE, "broker.rabbitmq")

                await relay.up()

                expect(await thread.poll(published, 0.2, 15.0)).true()

                found = [await broker.get(queue, 2.0), await broker.get(queue, 2.0)]

                expect(sorted(parcel.body for parcel in found if parcel)).equals([b"after", b"before"])

                for parcel in found:

                    if parcel: await broker.ack(parcel)

                expect(relay.opened).above(1)

            finally:

                await broker.purge(queue)
                await broker.close()

    async def test_a_rabbit_subscriber_resumes_and_loses_nothing_sent_while_it_was_cut ( self ) -> None:

        topic  = f"topic-{rand.hex(3)}"
        inbox  = f"{topic}.inbox"
        stop   = asyncio.Event()
        direct = RabbitBroker(AMQP, f"unit-{rand.hex(3)}", 4)
        heard: list[bytes] = []

        async def receive ( parcel: Parcel ) -> None:

            heard.append(parcel.body)

        async with test.relay("127.0.0.1", 5672) as relay:

            hurt = RabbitBroker(relay.url("amqp", "/?reconnect_interval=0.2", "guest:guest"), f"unit-{rand.hex(3)}", 4)

            await hurt.bind(topic, inbox, ("news.*",))

            listening = asyncio.create_task(hurt.subscribe(topic, inbox, receive, stop, ("news.*",)))

            try:

                await direct.broadcast(topic, "news.one", b"one")

                expect(await thread.poll(lambda: len(heard) >= 1, 0.05, 5.0)).true()

                relay.sever()

                await direct.broadcast(topic, "news.two", b"two")

                expect(await thread.poll(lambda: len(heard) >= 2, 0.1, 15.0)).true()
                expect((heard, relay.opened)).satisfies(lambda found: found[0] == [b"one", b"two"] and found[1] > 1)

            finally:

                stop.set()

                await asyncio.wait_for(listening, 5.0)
                await hurt.close()
                await direct.close()

    async def test_rabbit_workers_outlive_an_outage_and_an_unacked_job_comes_back ( self ) -> None:

        exchange = f"unit-{rand.hex(3)}"
        name     = f"work-{rand.hex(3)}"
        sender   = Queue()
        held     = asyncio.Event()
        free     = asyncio.Event()
        done: list[int] = []

        async def work ( value: int ) -> None:

            if value == 2 and not free.is_set():

                held.set()

                await free.wait()

            done.append(value)

        sender.setup(RabbitDriver(AMQP, exchange, 4), (name,))

        async with test.relay("127.0.0.1", 5672) as relay:

            worker = Queue()

            target = relay.url("amqp", "/?reconnect_interval=0.2", "guest:guest")

            worker.setup(RabbitDriver(target, exchange, 4), (name,))
            worker.register(worker.name_of(work), work)

            try:

                expect(worker.start(1)).equals(1)

                await sender.push(work, 1, queue=name)
                await sender.push(work, 2, queue=name)

                expect(await thread.poll(held.is_set, 0.05, 5.0)).true()

                opened = relay.opened

                relay.sever()

                expect(await thread.poll(lambda: relay.opened > opened, 0.05, 5.0)).true()

                free.set()

                def settled () -> bool:

                    return done == [1, 2, 2] and worker.describe()["busy"] == 0

                expect(await thread.poll(settled, 0.05, 10.0)).true()

                await relay.down()
                await sender.push(work, 3, queue=name)
                await asyncio.sleep(1.5)

                stalled = worker.describe()

                expect((stalled["workers"], done)).equals((1, [1, 2, 2]))
                expect(stalled["stalls"]).above(0)

                await relay.up()

                expect(await thread.poll(lambda: 3 in done, 0.1, 15.0)).true()
                expect(done[:3]).equals([1, 2, 2])
                expect([value for value in done[3:] if value != 2]).equals([3])
                expect(done[3:].count(2)).below(2)
                expect(worker.describe()["workers"]).equals(1)

            finally:

                await worker.close()
                await sender.driver().clear(name)
                await sender.close()
