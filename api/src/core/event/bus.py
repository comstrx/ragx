from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue, AbstractRobustConnection
from aio_pika.exceptions import AMQPError
from core.exceptions import Code, Fault
from core.json import json
from core.log import log
import asyncio

type Envelope = dict[str, Any]
type Handler = Callable[[Envelope], Awaitable[None]]

JSON = "application/json"

class Bus(Protocol):

    @property
    def name ( self ) -> str: ...

    @property
    def local ( self ) -> bool: ...

    async def publish ( self, envelope: Envelope ) -> None: ...

    async def consume ( self, handler: Handler, stop: asyncio.Event ) -> None: ...

    async def close ( self ) -> None: ...

class LocalBus:

    name  = "local"
    local = True

    async def publish ( self, _envelope: Envelope ) -> None:
        return None

    async def consume ( self, _handler: Handler, stop: asyncio.Event ) -> None:
        await stop.wait()

    async def close ( self ) -> None:
        return None

class RabbitBus:

    name  = "rabbitmq"
    local = False

    def __init__ (
        self, url: str, exchange: str = "events", queue: str = "events.listeners", prefetch: int = 32,
    ) -> None:

        self._url      = url
        self._name     = exchange
        self._queue    = queue
        self._prefetch = prefetch
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None

    async def open ( self ) -> AbstractExchange:

        if self._exchange is not None: return self._exchange

        try:

            self._connection = await connect_robust(self._url)
            self._channel    = await self._connection.channel()

            await self._channel.set_qos(prefetch_count=self._prefetch)

            self._exchange = await self._channel.declare_exchange(self._name, ExchangeType.TOPIC, durable=True)

        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="events") from error

        return self._exchange

    async def inbox ( self, pattern: str = "#" ) -> AbstractQueue:

        exchange = await self.open()

        if self._channel is None: raise Fault(Code.UNAVAILABLE, reason="events")

        try:

            queue = await self._channel.declare_queue(self._queue, durable=True, arguments={ "x-queue-type": "quorum" })

            await queue.bind(exchange, pattern)

        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="events") from error

        return queue

    async def publish ( self, envelope: Envelope ) -> None:

        exchange = await self.open()
        message  = Message(
            json.encode(envelope), content_type=JSON, delivery_mode=DeliveryMode.PERSISTENT,
            message_id=str(envelope.get("id", "")), type=str(envelope.get("kind", "")),
        )

        try: await exchange.publish(message, routing_key=self.route(str(envelope.get("kind", ""))))
        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="events") from error

    def route ( self, kind: str ) -> str:
        return kind.replace(":", ".").replace("_", "-")

    async def consume ( self, handler: Handler, stop: asyncio.Event ) -> None:

        queue = await self.inbox()

        async with queue.iterator() as messages:

            async for message in messages:

                if stop.is_set(): break

                try:

                    await handler(json.loads(message.body))
                    await message.ack()

                except Exception:

                    log.exception("events.rejected", id=message.message_id)

                    await message.reject(requeue=False)

    async def close ( self ) -> None:

        connection, self._connection = self._connection, None

        self._channel  = None
        self._exchange = None

        if connection is not None: await connection.close()
