from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from core.adapter import Adapter
from core.error import Fault
from core.log import log
import asyncio

type Consumer = Callable[[Parcel], Awaitable[None]]

QUEUES   = "queues"
DELAY    = "delay"
TOPICS   = "topics"
SIZE     = "size"
PURGE    = "purge"
ORDERED  = "ordered"
FEATURES = frozenset({QUEUES, DELAY, TOPICS, SIZE, PURGE})

@dataclass(frozen=True, slots=True, kw_only=True)
class Parcel:

    body     : bytes
    route    : str = ""
    id       : str = ""
    kind     : str = ""
    headers  : Mapping[str, Any] = field(default_factory=dict)
    receipt  : Any = field(default=None, compare=False, repr=False)
    replayed : bool = False

    def dump ( self ) -> dict[str, Any]:

        return {
            "route": self.route, "id": self.id, "kind": self.kind, "bytes": len(self.body), "replayed": self.replayed,
        }

def walk ( binding: list[str], route: list[str] ) -> bool:

    if not binding: return not route

    head = binding[0]

    if head == "#": return walk(binding[1:], route) or (bool(route) and walk(binding, route[1:]))
    if not route: return False

    return head in ("*", route[0]) and walk(binding[1:], route[1:])

def matches ( binding: str, route: str ) -> bool:

    return walk(binding.split("."), route.split(".") if route else [])

class Broker(Adapter, ABC):

    family       : ClassVar[str] = "broker"
    capabilities : ClassVar[frozenset[str]] = FEATURES

    @abstractmethod
    async def publish (
        self, queue: str, body: bytes, *, key: str = "", kind: str = "", headers: Mapping[str, Any] | None = None,
        delay: float = 0.0,
    ) -> None: ...

    @abstractmethod
    async def get ( self, queue: str, wait: float = 0.0 ) -> Parcel | None: ...

    @abstractmethod
    async def ack ( self, parcel: Parcel ) -> None: ...

    @abstractmethod
    async def reject ( self, parcel: Parcel, requeue: bool = False ) -> None: ...

    @abstractmethod
    async def size ( self, queue: str ) -> int: ...

    @abstractmethod
    async def purge ( self, queue: str ) -> int: ...

    @abstractmethod
    async def broadcast (
        self, topic: str, route: str, body: bytes, *, key: str = "", kind: str = "",
        headers: Mapping[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    async def bind ( self, topic: str, inbox: str, patterns: tuple[str, ...] = ("#",) ) -> None: ...

    @abstractmethod
    async def subscribe (
        self, topic: str, inbox: str, consumer: Consumer, stop: asyncio.Event, patterns: tuple[str, ...] = ("#",),
    ) -> None: ...

    async def handle ( self, parcel: Parcel, consumer: Consumer ) -> bool:

        try: await consumer(parcel)
        except Exception as error:

            kind = type(error).__name__

            log.exception("broker.rejected", broker=self.name, route=parcel.route, id=parcel.id, error=kind)

            return await self.settle(parcel, kept=False)

        return await self.settle(parcel, kept=True)

    async def settle ( self, parcel: Parcel, kept: bool ) -> bool:

        try: await (self.ack(parcel) if kept else self.reject(parcel))
        except Fault as fault:

            log.warning("broker.unsettled", broker=self.name, route=parcel.route, id=parcel.id, reason=fault.reason)

            return False

        return kept
