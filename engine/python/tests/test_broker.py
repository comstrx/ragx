from collections.abc import AsyncIterator

from engine.broker import Broker, Brokers, MemoryBroker, Parcel, RabbitBroker, matches
from engine.error import Code
from engine.rand import rand
from engine.test import expect, test
from engine.thread import thread
import asyncio, contextlib, pytest

AMQP = "amqp://guest:guest@127.0.0.1:5672/"

@pytest.fixture(params=["memory", "rabbitmq"])
async def broker ( request: pytest.FixtureRequest ) -> AsyncIterator[Broker]:

    remote = RabbitBroker(AMQP, f"unit-{rand.hex(3)}", 8, quorum=False)
    made   = MemoryBroker() if request.param == "memory" else remote

    try: yield made
    finally: await made.close()

@pytest.mark.anyio
class TestBroker:

    async def test_work_queues_carry_delay_ack_requeue_and_purge_alike ( self, broker: Broker ) -> None:

        queue = f"work-{rand.hex(3)}"

        expect(await broker.purge(queue)).equals(0)

        await broker.publish(queue, b"one", key="m1", kind="unit", headers={ "attempts": 2 })
        await broker.publish(queue, b"late", key="m2", delay=0.3)

        expect(await thread.poll(lambda: _sized(broker, queue, 2), 0.05, 3.0)).true()

        first = await broker.get(queue, 1.0)

        expect(first).some()
        expect((first.body, first.id, first.kind, first.headers.get("attempts")) if first else None).equals(
            (b"one", "m1", "unit", 2),
        )
        expect(await broker.get(queue, 0.05)).none()

        if first: await broker.reject(first, requeue=True)

        again = await broker.get(queue, 2.0)

        expect((again.body, again.replayed) if again else None).equals((b"one", True))

        if again: await broker.ack(again)

        late = await broker.get(queue, 3.0)

        expect(late.body if late else None).equals(b"late")

        if late: await broker.ack(late)

        await broker.publish(queue, b"x")
        await broker.publish(queue, b"y")

        expect(await thread.poll(lambda: _sized(broker, queue, 2), 0.05, 3.0)).true()
        expect((await broker.purge(queue), await broker.size(queue))).equals((2, 0))

    async def test_topics_fan_out_by_pattern_and_stop_gracefully ( self, broker: Broker ) -> None:

        topic = f"topic-{rand.hex(3)}"
        stop  = asyncio.Event()
        heard: list[str] = []

        async def receive ( parcel: Parcel ) -> None:

            if parcel.body == b"boom": raise RuntimeError(parcel.route)

            heard.append(parcel.route)

        await broker.bind(topic, f"{topic}.inbox", ("orders.*", "users.#"))

        await broker.broadcast(topic, "orders.paid", b"1", key="e1")
        await broker.broadcast(topic, "orders.paid.late", b"2")
        await broker.broadcast(topic, "users.created.admin", b"3")
        await broker.broadcast(topic, "orders.paid", b"boom")
        await broker.broadcast(topic, "audit.log", b"4")

        listening = asyncio.create_task(broker.subscribe(topic, f"{topic}.inbox", receive, stop, ("orders.*",)))

        expect(await thread.poll(lambda: len(heard) >= 2, 0.05, 5.0)).true()

        stop.set()

        await asyncio.wait_for(listening, 3.0)

        expect(sorted(heard)).equals(["orders.paid", "users.created.admin"])

    async def test_a_cancelled_get_keeps_the_broker_usable_and_the_message_queued ( self, broker: Broker ) -> None:

        queue = f"work-{rand.hex(3)}"

        expect(await broker.purge(queue)).equals(0)

        for turn in range(30):

            await broker.publish(queue, b"kept", key=f"k{turn}")

            expect(await thread.poll(lambda: _sized(broker, queue, 1), 0.05, 3.0)).true()

            pull   = asyncio.ensure_future(broker.get(queue, 1.0))
            parcel = None

            for _ in range(turn % 6): await asyncio.sleep(0)

            pull.cancel()

            with contextlib.suppress(asyncio.CancelledError): parcel = await pull

            parcel = parcel or await broker.get(queue, 2.0)

            expect(parcel.id if parcel else None).equals(f"k{turn}")

            if parcel: await broker.ack(parcel)

        expect(await broker.size(queue)).equals(0)

class TestFacade:

    def test_topic_patterns_and_the_registry_follow_amqp_rules ( self ) -> None:

        expect([matches("a.*", "a.b"), matches("a.*", "a.b.c"), matches("a.#", "a"), matches("#.c", "a.b.c")]).equals(
            [True, False, True, True],
        )
        expect([matches("*.b.#", "x.b"), matches("a.b", "a.b"), matches("a", ""), matches("#", "")]).equals(
            [True, True, False, True],
        )

        own = Brokers()

        own.connect("memory")
        own.connect("rabbitmq", url=AMQP, exchange="jobs")

        expect(own.describe()["providers"]).equals(["memory", "rabbitmq"])

        with test.fails(Code.INTERNAL, "broker.kafka.planned"): own.connect("kafka")
        with test.fails(Code.INTERNAL, "broker.nats.missing"): own.connect("nats")

async def _sized ( broker: Broker, queue: str, count: int ) -> bool:

    return await broker.size(queue) == count
