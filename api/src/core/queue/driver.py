from collections.abc import Callable
from typing import Any, Protocol

from core.broker import Broker, MemoryBroker, Parcel, RabbitBroker
from core.error import Code, Fault
from core.json import json
from .job import DEFAULT, Job

type Handler = Callable[..., Any]

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    async def push ( self, job: Job ) -> None: ...

    async def pull ( self, queue: str, wait: float ) -> Job | None: ...

    async def size ( self, queue: str ) -> int: ...

    async def clear ( self, queue: str ) -> int: ...

    async def ack ( self, job: Job ) -> None: ...

    async def close ( self ) -> None: ...

class BrokerDriver:

    def __init__ ( self, broker: Broker ) -> None:

        self._broker = broker
        self.name    = broker.name

    def broker ( self ) -> Broker:

        return self._broker

    async def push ( self, job: Job ) -> None:

        body = json.encode(job.dump())

        tried = { "attempts": job.attempts }

        await self._broker.publish(job.queue, body, key=job.id, kind=job.name, headers=tried, delay=job.delay())

    async def pull ( self, queue: str, wait: float ) -> Job | None:

        parcel = await self._broker.get(queue, wait)

        return None if parcel is None else Job.load(json.loads(parcel.body), receipt=parcel)

    async def size ( self, queue: str ) -> int:

        return await self._broker.size(queue)

    async def clear ( self, queue: str ) -> int:

        return await self._broker.purge(queue)

    async def ack ( self, job: Job ) -> None:

        if isinstance(job.receipt, Parcel): await self._broker.ack(job.receipt)

    async def close ( self ) -> None:

        await self._broker.close()

class MemoryDriver(BrokerDriver):

    def __init__ ( self ) -> None:

        self._memory = MemoryBroker()

        super().__init__(self._memory)

    def peek ( self, queue: str, limit: int = 20 ) -> list[Job]:

        return [Job.load(json.loads(parcel.body)) for parcel in self._memory.peek(queue, limit)]

    def queues ( self ) -> list[str]:

        return self._memory.queues()

class RabbitDriver(BrokerDriver):

    def __init__ ( self, url: str, exchange: str = "jobs", prefetch: int = 16, quorum: bool = True ) -> None:

        super().__init__(RabbitBroker(url, exchange, prefetch, quorum))

class SyncDriver:

    name = "sync"

    async def push ( self, _job: Job ) -> None:

        return None

    async def pull ( self, _queue: str, _wait: float ) -> Job | None:

        return None

    async def size ( self, _queue: str ) -> int:

        return 0

    async def clear ( self, _queue: str ) -> int:

        return 0

    async def ack ( self, _job: Job ) -> None:

        return None

    async def close ( self ) -> None:

        return None

class Board:

    def __init__ ( self ) -> None:

        self._driver: Driver | None = None
        self._handlers: dict[str, Handler] = {}
        self._queues: tuple[str, ...] = (DEFAULT,)

    def ready ( self ) -> bool:

        return self._driver is not None

    def driver ( self ) -> Driver:

        if self._driver is None: raise Fault(Code.INTERNAL, reason="queue")

        return self._driver

    def inline ( self ) -> bool:

        return self._driver is None or self._driver.name == "sync"

    def queues ( self ) -> tuple[str, ...]:

        return self._queues

    def register ( self, name: str, handler: Handler ) -> str:

        self._handlers[name] = handler

        return name

    def name_of ( self, handler: Handler ) -> str:

        return f"{handler.__module__}:{handler.__qualname__}"

    def handler ( self, name: str ) -> Handler:

        found = self._handlers.get(name)

        if found is None: raise Fault(Code.INTERNAL, reason=f"queue.{name}")

        return found

    def names ( self ) -> list[str]:

        return sorted(self._handlers)

    async def size ( self, queue: str | None = None ) -> int:

        return await self.driver().size(queue or self._queues[0])

    async def sizes ( self ) -> dict[str, int]:

        return { name: await self.driver().size(name) for name in self._queues }

    async def clear ( self, queue: str | None = None ) -> int:

        return await self.driver().clear(queue or self._queues[0])

    async def clear_all ( self ) -> int:

        return sum([await self.driver().clear(name) for name in self._queues])
