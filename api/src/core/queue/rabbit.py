from typing import Any

from aio_pika import DeliveryMode, ExchangeType, Message, connect_robust
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractQueue, AbstractRobustConnection
from aio_pika.exceptions import AMQPError
from core.date import date
from core.error import Code, Fault
from core.json import json
from .job import Job

JSON = "application/json"

class RabbitDriver:

    name = "rabbitmq"

    def __init__ ( self, url: str, exchange: str = "jobs", prefetch: int = 16, quorum: bool = True ) -> None:

        self._url      = url
        self._name     = exchange
        self._prefetch = prefetch
        self._quorum   = quorum
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._queues: dict[str, AbstractQueue] = {}

    async def open ( self ) -> None:

        if self._connection is not None: return

        try:

            self._connection = await connect_robust(self._url)
            self._channel    = await self._connection.channel()

            await self._channel.set_qos(prefetch_count=self._prefetch)

            self._exchange = await self._channel.declare_exchange(self._name, ExchangeType.DIRECT, durable=True)

        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

    async def close ( self ) -> None:

        connection, self._connection = self._connection, None

        self._channel  = None
        self._exchange = None
        self._queues   = {}

        if connection is not None: await connection.close()

    async def exchange ( self ) -> AbstractExchange:

        await self.open()

        if self._exchange is None: raise Fault(Code.UNAVAILABLE, reason="queue")

        return self._exchange

    async def ready ( self, queue: str ) -> AbstractQueue:

        if queue in self._queues: return self._queues[queue]

        await self.open()

        if self._channel is None: raise Fault(Code.UNAVAILABLE, reason="queue")

        kind: dict[str, Any] = { "x-queue-type": "quorum" } if self._quorum else {}

        try:

            live = await self._channel.declare_queue(f"{self._name}.{queue}", durable=True, arguments=kind)
            wait = await self._channel.declare_queue(
                f"{self._name}.{queue}.wait", durable=True,
                arguments={ "x-dead-letter-exchange": self._name, "x-dead-letter-routing-key": queue },
            )

            await live.bind(self._exchange or await self.exchange(), queue)
            await wait.bind(self._exchange or await self.exchange(), f"{queue}.wait")

        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

        self._queues[queue] = live

        return live

    async def push ( self, job: Job ) -> None:

        await self.ready(job.queue)

        delay   = max(job.available - date.stamp(), 0.0)
        message = Message(
            json.encode(job.dump()), content_type=JSON, delivery_mode=DeliveryMode.PERSISTENT, message_id=job.id,
            headers={ "attempts": job.attempts }, expiration=delay if delay > 0 else None,
        )

        try: await (await self.exchange()).publish(message, routing_key=f"{job.queue}.wait" if delay > 0 else job.queue)
        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

    async def pull ( self, queue: str, wait: float ) -> Job | None:

        live = await self.ready(queue)

        try: message = await live.get(no_ack=False, fail=False, timeout=max(wait, 0.01))
        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

        if message is None: return None

        return Job.load(json.loads(message.body), receipt=message)

    async def ack ( self, job: Job ) -> None:

        receipt = job.receipt

        if receipt is not None and hasattr(receipt, "ack"): await receipt.ack()

    async def size ( self, queue: str ) -> int:

        live = await self.ready(queue)

        if self._channel is None: return 0

        try:

            underlay = await self._channel.get_underlay_channel()
            declared = await underlay.queue_declare(live.name, passive=True, durable=True)

        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

        return int(getattr(declared, "message_count", 0) or 0)

    async def clear ( self, queue: str ) -> int:

        live  = await self.ready(queue)
        count = await self.size(queue)

        try: await live.purge()
        except (AMQPError, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="queue") from error

        return count
