from collections.abc import Mapping
from dataclasses import replace
from typing import Any, ClassVar, override

from core.adapter import Manager
from core.date import date
from core.error import Code, Fault
from .broker import FEATURES, ORDERED, Broker, Consumer, Parcel, matches
from .rabbit import RabbitBroker
import asyncio, heapq, itertools

type Entry = tuple[float, int, Parcel]
PLANNED = ("kafka", "redpanda")

class MemoryBroker(Broker):

    name         = "memory"
    capabilities : ClassVar[frozenset[str]] = FEATURES | frozenset({ORDERED})

    def __init__ ( self ) -> None:

        self._heaps: dict[str, list[Entry]] = {}
        self._wakeups: dict[str, asyncio.Event] = {}
        self._inboxes: dict[str, dict[str, tuple[tuple[str, ...], asyncio.Queue[Parcel]]]] = {}
        self._order = itertools.count()
        self._held: dict[str, Parcel] = {}

    def heap ( self, queue: str ) -> list[Entry]:

        return self._heaps.setdefault(queue, [])

    def wakeup ( self, queue: str ) -> asyncio.Event:

        return self._wakeups.setdefault(queue, asyncio.Event())

    @override
    async def publish (
        self, queue: str, body: bytes, *, key: str = "", kind: str = "", headers: Mapping[str, Any] | None = None,
        delay: float = 0.0,
    ) -> None:

        parcel = Parcel(
            body=body, route=queue, id=key, kind=kind, headers=dict(headers or {}), receipt=next(self._order),
        )

        self.put(parcel, date.stamp() + max(delay, 0.0))

    def put ( self, parcel: Parcel, available: float ) -> None:

        heapq.heappush(self.heap(parcel.route), (available, next(self._order), parcel))

        self.wakeup(parcel.route).set()

    @override
    async def get ( self, queue: str, wait: float = 0.0 ) -> Parcel | None:

        heap     = self.heap(queue)
        deadline = date.stamp() + max(wait, 0.0)

        while True:

            now = date.stamp()

            if heap and heap[0][0] <= now:

                parcel = heapq.heappop(heap)[2]

                self._held[str(parcel.receipt)] = parcel

                return parcel

            remaining = deadline - now

            if remaining <= 0: return None

            pause = min(remaining, heap[0][0] - now) if heap else remaining
            flag  = self.wakeup(queue)

            flag.clear()

            try:
                async with asyncio.timeout(max(pause, 0.001)): await flag.wait()
            except TimeoutError: continue

    @override
    async def ack ( self, parcel: Parcel ) -> None:

        self._held.pop(str(parcel.receipt), None)

    @override
    async def reject ( self, parcel: Parcel, requeue: bool = False ) -> None:

        held = self._held.pop(str(parcel.receipt), None)

        if requeue and held is not None: self.put(replace(held, receipt=next(self._order), replayed=True), date.stamp())

    @override
    async def size ( self, queue: str ) -> int:

        return len(self.heap(queue))

    @override
    async def purge ( self, queue: str ) -> int:

        count = len(self.heap(queue))

        self.heap(queue).clear()

        return count

    def peek ( self, queue: str, limit: int = 20 ) -> list[Parcel]:

        return [entry[2] for entry in heapq.nsmallest(limit, self.heap(queue))]

    def queues ( self ) -> list[str]:

        return sorted(name for name, heap in self._heaps.items() if heap)

    @override
    async def broadcast (
        self, topic: str, route: str, body: bytes, *, key: str = "", kind: str = "",
        headers: Mapping[str, Any] | None = None,
    ) -> None:

        parcel = Parcel(body=body, route=route, id=key, kind=kind, headers=dict(headers or {}))

        for patterns, inbox in self._inboxes.get(topic, {}).values():

            if any(matches(pattern, route) for pattern in patterns): inbox.put_nowait(parcel)

    def mailbox ( self, topic: str, inbox: str, patterns: tuple[str, ...] ) -> asyncio.Queue[Parcel]:

        bindings = self._inboxes.setdefault(topic, {})
        held     = bindings[inbox][1] if inbox in bindings else asyncio.Queue[Parcel]()
        known    = bindings[inbox][0] if inbox in bindings else ()

        bindings[inbox] = (tuple(dict.fromkeys((*known, *patterns))), held)

        return held

    @override
    async def bind ( self, topic: str, inbox: str, patterns: tuple[str, ...] = ("#",) ) -> None:

        self.mailbox(topic, inbox, patterns)

    @override
    async def subscribe (
        self, topic: str, inbox: str, consumer: Consumer, stop: asyncio.Event, patterns: tuple[str, ...] = ("#",),
    ) -> None:

        mailbox = self.mailbox(topic, inbox, patterns)

        while not stop.is_set():

            try:
                async with asyncio.timeout(0.05): parcel = await mailbox.get()
            except TimeoutError: continue

            await self.handle(parcel, consumer)

class Brokers(Manager[Broker]):

    def __init__ ( self ) -> None:

        super().__init__("broker")

    def connect ( self, name: str, default: bool = False, **settings: Any ) -> Broker:

        made: Broker

        match name:
            case "memory": made = MemoryBroker()
            case "rabbitmq":
                made = RabbitBroker(
                    str(settings.get("url", "")), str(settings.get("exchange", "jobs")),
                    int(settings.get("prefetch", 16)), bool(settings.get("quorum", True)),
                )
            case _ if name in PLANNED: raise Fault(Code.INTERNAL, reason=f"broker.{name}.planned")
            case _: raise Fault(Code.INTERNAL, reason=f"broker.{name}.missing")

        return self.register(made, default)

    async def publish (
        self, queue: str, body: bytes, delay: float = 0.0, headers: Mapping[str, Any] | None = None,
        using: str | None = None,
    ) -> None:

        await self.use(using).publish(queue, body, headers=headers, delay=delay)

    async def get ( self, queue: str, wait: float = 0.0, using: str | None = None ) -> Parcel | None:

        return await self.use(using).get(queue, wait)

    async def broadcast ( self, topic: str, route: str, body: bytes, using: str | None = None ) -> None:

        await self.use(using).broadcast(topic, route, body)

    async def subscribe (
        self, topic: str, inbox: str, consumer: Consumer, stop: asyncio.Event, patterns: tuple[str, ...] = ("#",),
        using: str | None = None,
    ) -> None:

        await self.use(using).subscribe(topic, inbox, consumer, stop, patterns)
