from collections.abc import Mapping
from typing import Any, ClassVar, override

from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import (
    AbstractChannel, AbstractExchange, AbstractIncomingMessage, AbstractQueue, AbstractRobustConnection,
)
from aio_pika.exceptions import AMQPError
from core.date import date
from core.error import Code, Fault
from .broker import FEATURES, Broker, Consumer, Parcel
import asyncio, contextlib

JSON  = "application/octet-stream"
RPC   = 5.0
NAP   = 0.05
FAULT = (AMQPError, OSError, RuntimeError)

class RabbitBroker(Broker):

    name         = "rabbitmq"
    capabilities : ClassVar[frozenset[str]] = FEATURES

    def __init__ ( self, url: str, exchange: str = "jobs", prefetch: int = 16, quorum: bool = True ) -> None:

        self._url      = url
        self._name     = exchange
        self._prefetch = prefetch
        self._quorum   = quorum
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchanges: dict[str, AbstractExchange] = {}
        self._queues: dict[str, AbstractQueue] = {}
        self._lock     = asyncio.Lock()

    def unavailable ( self, error: BaseException | None = None ) -> Fault:

        fault = Fault(Code.UNAVAILABLE, reason=f"broker.{self.name}")

        if error is not None: fault.__cause__ = error

        return fault

    async def _channel_ ( self ) -> AbstractChannel:

        async with self._lock:

            if self._channel is not None and not self._channel.is_closed: return self._channel

            try:

                self._connection = self._connection or await connect_robust(self._url)
                self._channel    = await self._connection.channel()

                self._exchanges.clear()
                self._queues.clear()

                await self._channel.set_qos(prefetch_count=self._prefetch)

            except FAULT as error: raise self.unavailable(error) from error

            return self._channel

    async def _exchange_ ( self, name: str, kind: ExchangeType = ExchangeType.DIRECT ) -> AbstractExchange:

        if name in self._exchanges: return self._exchanges[name]

        channel = await self._channel_()

        try: found = await channel.declare_exchange(name, kind, durable=True)
        except FAULT as error: raise self.unavailable(error) from error

        self._exchanges[name] = found

        return found

    def arguments ( self ) -> dict[str, Any]:

        return { "x-queue-type": "quorum" } if self._quorum else {}

    async def _queue_ ( self, name: str ) -> AbstractQueue:

        if name in self._queues: return self._queues[name]

        channel  = await self._channel_()
        exchange = await self._exchange_(self._name)

        try:

            live = await channel.declare_queue(f"{self._name}.{name}", durable=True, arguments=self.arguments())
            wait = await channel.declare_queue(
                f"{self._name}.{name}.wait", durable=True,
                arguments={ "x-dead-letter-exchange": self._name, "x-dead-letter-routing-key": name },
            )

            await live.bind(exchange, name)
            await wait.bind(exchange, f"{name}.wait")

        except FAULT as error: raise self.unavailable(error) from error

        self._queues[name] = live

        return live

    def _message_ (
        self, body: bytes, key: str, kind: str, headers: Mapping[str, Any] | None, delay: float = 0.0,
    ) -> Message:

        return Message(
            body, content_type=JSON, delivery_mode=DeliveryMode.PERSISTENT, message_id=key or None, type=kind or None,
            headers=dict(headers or {}), expiration=delay if delay > 0 else None,
        )

    @override
    async def publish (
        self, queue: str, body: bytes, *, key: str = "", kind: str = "", headers: Mapping[str, Any] | None = None,
        delay: float = 0.0,
    ) -> None:

        await self._queue_(queue)

        route    = f"{queue}.wait" if delay > 0 else queue
        exchange = await self._exchange_(self._name)

        try: await exchange.publish(self._message_(body, key, kind, headers, delay), routing_key=route)
        except FAULT as error: raise self.unavailable(error) from error

    @override
    async def get ( self, queue: str, wait: float = 0.0 ) -> Parcel | None:

        live     = await self._queue_(queue)
        deadline = date.stamp() + max(wait, 0.0)

        while True:

            try: found = await live.get(no_ack=False, fail=False, timeout=RPC)
            except FAULT as error: raise self.unavailable(error) from error

            if found is not None: return self._parcel_(found, queue)
            if date.stamp() >= deadline: return None

            await asyncio.sleep(min(NAP, max(deadline - date.stamp(), 0.0)))

    def _parcel_ ( self, found: AbstractIncomingMessage, route: str ) -> Parcel:

        return Parcel(
            body=found.body, route=found.routing_key or route, id=found.message_id or "", kind=found.type or "",
            headers=dict(found.headers or {}), receipt=found, replayed=bool(found.redelivered),
        )

    @override
    async def ack ( self, parcel: Parcel ) -> None:

        if not isinstance(parcel.receipt, AbstractIncomingMessage): return

        try: await parcel.receipt.ack()
        except FAULT as error: raise self.unavailable(error) from error

    @override
    async def reject ( self, parcel: Parcel, requeue: bool = False ) -> None:

        if not isinstance(parcel.receipt, AbstractIncomingMessage): return

        try: await parcel.receipt.reject(requeue=requeue)
        except FAULT as error: raise self.unavailable(error) from error

    async def counted ( self, name: str ) -> int:

        channel = await self._channel_()

        try:
            underlay = await channel.get_underlay_channel()
            declared = await underlay.queue_declare(name, passive=True, durable=True)
        except FAULT as error: raise self.unavailable(error) from error

        return int(getattr(declared, "message_count", 0) or 0)

    @override
    async def size ( self, queue: str ) -> int:

        live = await self._queue_(queue)

        return await self.counted(live.name) + await self.counted(f"{live.name}.wait")

    @override
    async def purge ( self, queue: str ) -> int:

        live    = await self._queue_(queue)
        count   = await self.size(queue)
        channel = await self._channel_()

        try:
            await live.purge()
            await (await channel.get_queue(f"{live.name}.wait", ensure=False)).purge()
        except FAULT as error: raise self.unavailable(error) from error

        return count

    @override
    async def broadcast (
        self, topic: str, route: str, body: bytes, *, key: str = "", kind: str = "",
        headers: Mapping[str, Any] | None = None,
    ) -> None:

        exchange = await self._exchange_(topic, ExchangeType.TOPIC)

        try: await exchange.publish(self._message_(body, key, kind, headers), routing_key=route)
        except FAULT as error: raise self.unavailable(error) from error

    async def _inbox_ ( self, topic: str, inbox: str, patterns: tuple[str, ...] ) -> AbstractQueue:

        channel  = await self._channel_()
        exchange = await self._exchange_(topic, ExchangeType.TOPIC)

        try:

            queue = await channel.declare_queue(inbox, durable=True, arguments={ "x-queue-type": "quorum" })

            for pattern in patterns: await queue.bind(exchange, pattern)

        except FAULT as error: raise self.unavailable(error) from error

        return queue

    @override
    async def bind ( self, topic: str, inbox: str, patterns: tuple[str, ...] = ("#",) ) -> None:

        await self._inbox_(topic, inbox, patterns)

    @override
    async def subscribe (
        self, topic: str, inbox: str, consumer: Consumer, stop: asyncio.Event, patterns: tuple[str, ...] = ("#",),
    ) -> None:

        queue = await self._inbox_(topic, inbox, patterns)
        busy  = asyncio.Lock()

        async def receive ( found: AbstractIncomingMessage ) -> None:

            async with busy: await self.handle(self._parcel_(found, inbox), consumer)

        try: tag = await queue.consume(receive)
        except FAULT as error: raise self.unavailable(error) from error

        try: await stop.wait()
        finally:

            with contextlib.suppress(*FAULT): await queue.cancel(tag)

            async with busy: pass

    @override
    async def close ( self ) -> None:

        connection, self._connection = self._connection, None

        self._channel   = None
        self._exchanges = {}
        self._queues    = {}

        if connection is not None: await connection.close()

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "exchange": self._name, "prefetch": self._prefetch, "quorum": self._quorum }
