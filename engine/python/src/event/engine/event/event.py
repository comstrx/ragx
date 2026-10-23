from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, ClassVar, Protocol, Self, override

from engine.broker import Broker, Parcel, RabbitBroker
from engine.error import Code, Fault
from engine.json import json
import asyncio

type Envelope = dict[str, Any]
type Handler = Callable[[Envelope], Awaitable[None]]

class Event:

    registry : ClassVar[dict[str, type[Event]]] = {}
    kind     : ClassVar[str] = ""

    @override
    def __init_subclass__ ( cls, **kwargs: object ) -> None:

        super().__init_subclass__(**kwargs)

        cls.kind = f"{cls.__module__}:{cls.__qualname__}"

        Event.registry[cls.kind] = cls

    def dump ( self ) -> dict[str, Any]:

        shaped: object = self
        data: Any      = asdict(shaped) if is_dataclass(shaped) and not isinstance(shaped, type) else dict(vars(self))
        plain: dict[str, Any] = json.loads(json.encode(data))

        return plain

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Self:

        return cls(**data)

    @classmethod
    def of ( cls, name: str, data: Mapping[str, Any] ) -> Event:

        kind = cls.registry.get(name)

        if kind is None: raise Fault(Code.INTERNAL, reason=f"event.{name}")

        return kind.load(data)

    @classmethod
    def kinds ( cls ) -> list[str]:

        return sorted(cls.registry)

    def channels ( self ) -> Sequence[str]:

        return ()

    def payload ( self ) -> dict[str, Any]:

        return self.dump()

    def label ( self ) -> str:

        return type(self).__name__

class Listener(Protocol):

    async def handle ( self, event: Any ) -> None: ...

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

class BrokerBus:

    local = False

    def __init__ ( self, broker: Broker, topic: str = "events", inbox: str = "events.listeners" ) -> None:

        self._broker = broker
        self._topic  = topic
        self._inbox  = inbox
        self.name    = broker.name

    def route ( self, kind: str ) -> str:

        return kind.replace(":", ".").replace("_", "-")

    async def publish ( self, envelope: Envelope ) -> None:

        kind = str(envelope.get("kind", ""))

        await self._broker.broadcast(
            self._topic, self.route(kind), json.encode(envelope), key=str(envelope.get("id", "")), kind=kind,
        )

    async def inbox ( self ) -> None:

        await self._broker.bind(self._topic, self._inbox)

    async def consume ( self, handler: Handler, stop: asyncio.Event ) -> None:

        async def receive ( parcel: Parcel ) -> None:

            await handler(json.loads(parcel.body))

        await self._broker.subscribe(self._topic, self._inbox, receive, stop)

    async def close ( self ) -> None:

        await self._broker.close()

class RabbitBus(BrokerBus):

    def __init__ (
        self, url: str, exchange: str = "events", queue: str = "events.listeners", prefetch: int = 32,
    ) -> None:

        super().__init__(RabbitBroker(url, f"{exchange}.direct", prefetch), exchange, queue)
