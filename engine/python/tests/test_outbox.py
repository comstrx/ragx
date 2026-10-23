from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, override

from engine.broadcast import Broadcast, RedisDriver
from engine.database import Outbox, Schema, database
from engine.event import Event, events
from engine.error import Code
from engine.http import App
from engine.queue import MemoryDriver, Queue
from engine.socket import Connection, Frame, Grant, Socket
from engine.rand import rand
from engine.test import expect, test
from engine.thread import thread
import asyncio, pytest

REDIS = "redis://127.0.0.1:6379/15"

async def arrived ( queue: asyncio.Queue[bytes], count: int ) -> int:

    for _ in range(100):

        if queue.qsize() >= count: break

        await asyncio.sleep(0.02)

    return queue.qsize()

@dataclass(frozen=True, slots=True)
class Shipped(Event):

    order : str

    @override
    def channels ( self ) -> Sequence[str]:

        return ("orders",)

class Sink:

    def __init__ ( self ) -> None:

        self.seen: list[Mapping[str, Any]] = []
        self.fail = 0

    async def __call__ ( self, payload: Mapping[str, Any] ) -> None:

        if self.fail > 0:

            self.fail -= 1

            raise ConnectionError(payload.get("n"))

        self.seen.append(dict(payload))

@pytest.fixture
async def box ( app: App ) -> AsyncIterator[Outbox]:

    name = f"scratch_outbox_{rand.hex(3)}"
    made = Outbox(database, name, grace=0.0, lease=30.0, backoff=0.01)

    async with database.transaction() as session: await Schema(session).create(name, Outbox.define)

    try: yield made
    finally:

        await made.stop()

        async with database.transaction() as session: await Schema(session).drop(name)

class TestOutbox:

    async def test_side_effects_leave_after_commit_and_vanish_on_rollback ( self, box: Outbox ) -> None:

        sink = Sink()

        box.kind("mail", sink)

        expect(await box.put("mail", { "n": 0 })).false()
        expect(sink.seen).equals([{ "n": 0 }])

        async with database.transaction():

            expect(await box.put("mail", { "n": 1 })).true()
            expect((await box.pending(), sink.seen)).equals((1, [{ "n": 0 }]))

        expect((sink.seen[-1], await box.pending())).equals(({ "n": 1 }, 0))

        with test.raises(RuntimeError, "rolled"):

            async with database.transaction():

                await box.put("mail", { "n": 2 })

                raise RuntimeError("rolled")

        async with database.transaction():

            async with database.transaction():
                await box.put("mail", { "n": 3 })

            with test.raises(RuntimeError):

                async with database.transaction():

                    await box.put("mail", { "n": 4 })

                    raise RuntimeError("inner")

        expect([item["n"] for item in sink.seen]).equals([0, 1, 3])
        expect(await box.pending()).equals(0)

        with test.fails(Code.INTERNAL, "outbox.kind"): await box.put("nowhere", {})

    async def test_failed_deliveries_wait_back_off_and_the_relay_brings_them_home ( self, box: Outbox ) -> None:

        sink = Sink()

        box.kind("hook", sink)

        sink.fail = 2

        async with database.transaction(): await box.put("hook", { "n": 7 })

        expect((sink.seen, await box.pending())).equals(([], 1))
        expect(box.describe()).subset({ "failed": 1, "sent": 0, "kinds": ["hook"] })

        await asyncio.sleep(0.03)

        expect(await box.relay()).equals(0)
        expect(await box.pending()).equals(1)

        await asyncio.sleep(0.05)

        expect(await box.relay()).equals(1)
        expect((sink.seen, await box.pending())).equals(([{ "n": 7 }], 0))
        expect(box.describe()).subset({ "failed": 2, "sent": 1, "relayed": 1 })

    async def test_concurrent_relays_deliver_each_row_once ( self, box: Outbox ) -> None:

        sink = Sink()

        box.kind("event", sink)

        sink.fail = 12

        async with database.transaction():
            for index in range(12): await box.put("event", { "n": index })

        expect(await box.pending()).equals(12)

        await asyncio.sleep(0.03)
        await database.fill(4)

        relayed = await thread.gather(*(box.relay(5) for _ in range(4)))

        expect(sum(relayed)).below(13)

        while await box.pending(): await box.relay()

        expect(sorted(item["n"] for item in sink.seen)).equals(list(range(12)))

    async def test_the_relay_runs_in_the_background_and_stops_gracefully ( self, box: Outbox ) -> None:

        sink = Sink()

        box.kind("tick", sink)

        sink.fail = 1

        async with database.transaction(): await box.put("tick", { "n": 1 })

        expect((box.start(0.02), box.start(0.02))).equals((True, False))
        expect(await thread.poll(lambda: bool(sink.seen), 0.02, 3.0)).true()
        expect((await box.stop(), await box.stop())).equals((True, False))
        expect(box.describe()["running"]).false()

    async def test_a_durable_queue_hands_its_jobs_to_the_outbox ( self, box: Outbox ) -> None:

        own  = Queue()
        done : list[int] = []

        async def work ( value: int ) -> None:

            done.append(value)

        own.setup(MemoryDriver())
        own.durable(box)

        async with database.transaction():

            await own.push(work, 5)

            expect(await own.size()).equals(0)

        expect(await own.size()).equals(1)
        expect(await own.drain()).equals(1)

        with test.raises(RuntimeError):

            async with database.transaction():

                await own.push(work, 6)

                raise RuntimeError("rolled")

        expect((await own.size(), done, box.kinds())).equals((0, [5], ["queue"]))

    async def test_a_durable_broadcast_frames_only_what_was_committed ( self, box: Outbox ) -> None:

        hub  = Socket()
        live = Broadcast()
        wire = test.stub()

        live.setup(hub)
        live.durable(box)

        listener = hub.attach(Connection("a", wire, outbox=asyncio.Queue(16)))

        hub.join(listener, "orders", Grant(allowed=True))

        async with database.transaction():

            await live.relay(Shipped("o-1"))

            expect(listener.outbox.qsize()).equals(0)

        expect(listener.outbox.qsize()).equals(1)

        with test.raises(RuntimeError):

            async with database.transaction():

                await live.relay(Shipped("o-2"))

                raise RuntimeError("rolled")

        expect((listener.outbox.qsize(), box.kinds(), await box.pending())).equals((1, ["broadcast"], 0))

        await live.stop()
        await events.dispatch(Shipped("o-3"))

        expect(listener.outbox.qsize()).equals(1)

    async def test_a_durable_broadcast_crosses_redis_after_commit_and_outlives_an_outage ( self, box: Outbox ) -> None:

        topic  = f"unit-{rand.hex(3)}"
        near   = Socket()
        far    = Socket()
        down   = Socket()
        live   = Broadcast()
        dead   = Broadcast()
        across = RedisDriver(far, REDIS, topic)
        reader = far.attach(Connection("far", test.stub(), outbox=asyncio.Queue(16)))
        cut    = down.attach(Connection("down", test.stub(), outbox=asyncio.Queue(16)))

        far.join(reader, "orders")
        down.join(cut, "orders")
        live.setup(near, driver=RedisDriver(near, REDIS, topic))
        dead.setup(down, driver=RedisDriver(down, "redis://127.0.0.1:1/15", topic, wait=0.5))

        try:

            await live.start()
            await across.start()

            dead.durable(box)

            async with database.transaction(): await dead.relay(Shipped("o-9"))

            expect((await box.pending(), cut.outbox.qsize(), reader.outbox.qsize())).equals((1, 0, 0))

            live.durable(box)

            await asyncio.sleep(0.03)

            expect(await box.relay()).equals(1)
            expect(await arrived(reader.outbox, 1)).equals(1)

            async with database.transaction():

                await live.relay(Shipped("o-1"))

                expect(reader.outbox.qsize()).equals(1)

            expect(await arrived(reader.outbox, 2)).equals(2)

            with test.raises(RuntimeError):

                async with database.transaction():

                    await live.relay(Shipped("o-2"))

                    raise RuntimeError("rolled")

            await asyncio.sleep(0.1)

            frames = [Frame.decode(reader.outbox.get_nowait()) for _ in range(reader.outbox.qsize())]

            expect([frame.data for frame in frames]).equals([{ "order": "o-9" }, { "order": "o-1" }])
            expect((await box.pending(), across.describe()["relayed"], across.describe()["lost"])).equals((0, 2, 0))

        finally:

            await live.stop()
            await across.stop()
            await dead.stop()
