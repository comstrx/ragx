from collections import deque
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, Self

from core.context import context
from core.date import date
from core.error import Code, Fault
from core.log import log
from core.queue import Queued, queue
from core.rand import rand
from .bus import Bus, Envelope, LocalBus
from .event import Event, Listener
import asyncio, contextlib, inspect

type Handler = Callable[[Any], Awaitable[None] | None]
type Target = Handler | type[Listener] | Listener

KEPT = 200

class Events:

    def __init__ ( self ) -> None:

        self._listeners: dict[type[Event], list[Target]] = {}
        self._named: dict[str, Target] = {}
        self._any: list[Handler] = []
        self._once: dict[type[Event], list[Handler]] = {}
        self._waiting: dict[type[Event], list[asyncio.Future[Any]]] = {}
        self._bus: Bus = LocalBus()
        self._stopping  = asyncio.Event()
        self._consumer: asyncio.Task[None] | None = None
        self._history: deque[Envelope] = deque(maxlen=KEPT)
        self._held: list[Event] | None = None
        self._recorded: list[Event] | None = None
        self._dispatched = 0

    def setup ( self, bus: Bus ) -> None:

        self._bus = bus

    def bus ( self ) -> Bus:

        return self._bus

    def listen ( self, kind: type[Event], *targets: Target ) -> Self:

        group = self._listeners.setdefault(kind, [])

        for target in targets:

            if target not in group: group.append(target)

            self._named[self.name_of(target)] = target

        return self

    def once ( self, kind: type[Event], handler: Handler ) -> Self:

        self._once.setdefault(kind, []).append(handler)

        return self

    def subscribe ( self, mapping: Mapping[type[Any], Sequence[Any]] ) -> Self:

        for kind, targets in mapping.items(): self.listen(kind, *targets)

        return self

    def on_any ( self, handler: Handler ) -> Self:

        if handler not in self._any: self._any.append(handler)

        return self

    def off ( self, kind: type[Event], target: Target ) -> bool:

        group = self._listeners.get(kind, [])

        if target not in group: return False

        group.remove(target)

        return True

    def forget ( self, kind: type[Event] ) -> bool:

        found = self._listeners.pop(kind, None) is not None

        return self._once.pop(kind, None) is not None or found

    def listeners ( self, kind: type[Event] ) -> list[Target]:

        return [target for known, group in self._listeners.items() if issubclass(kind, known) for target in group]

    def listener_names ( self, kind: type[Event] ) -> list[str]:

        return [self.name_of(target) for target in self.listeners(kind)]

    def has_listeners ( self, kind: type[Event] ) -> bool:

        return bool(self.listeners(kind)) or bool(self._once.get(kind))

    def kinds ( self ) -> list[str]:

        return sorted(kind.kind for kind in self._listeners)

    def name_of ( self, target: Target ) -> str:

        kind = target if isinstance(target, type) else (target if inspect.isfunction(target) else type(target))

        return f"{kind.__module__}:{kind.__qualname__}"

    def envelope ( self, event: Event ) -> Envelope:

        return { "id": str(rand.uuid()), "kind": event.kind, "data": event.dump(), "at": date.iso(date.now()) }

    async def dispatch ( self, event: Event ) -> int:

        if self._recorded is not None: self._recorded.append(event)
        if self._held is not None:

            self._held.append(event)

            return 0

        targets  = self.listeners(type(event))
        envelope = self.envelope(event)

        self._history.append(envelope)
        self._dispatched += 1

        if self._bus.local:
            for target in targets: await self.deliver(target, event)
        else: await context.defer(lambda: self._bus.publish(envelope))

        for handler in self._any: await self.call(handler, event)

        for handler in self._once.pop(type(event), []): await self.call(handler, event)

        for future in self._waiting.pop(type(event), []):
            if not future.done(): future.set_result(event)

        log.debug("event.dispatched", name=event.label(), listeners=len(targets))

        return len(targets)

    async def dispatch_if ( self, condition: object, event: Event ) -> int:

        return await self.dispatch(event) if condition else 0

    async def dispatch_unless ( self, condition: object, event: Event ) -> int:

        return await self.dispatch(event) if not condition else 0

    async def dispatch_many ( self, events: Sequence[Event] ) -> int:

        return sum([await self.dispatch(event) for event in events])

    async def deliver ( self, target: Target, event: Event ) -> None:

        instance = target() if isinstance(target, type) else target

        if isinstance(instance, Queued) and not queue.inline():

            await queue.push(
                self.replay, self.name_of(target), event.kind, event.dump(),
                queue=instance.queue, delay=instance.delay, tries=instance.tries, backoff=instance.backoff,
            )

            return

        await self.call(instance, event)

    async def receive ( self, envelope: Envelope ) -> None:

        event = Event.of(str(envelope["kind"]), dict(envelope.get("data", {})))

        for target in self.listeners(type(event)): await self.deliver(target, event)

        log.debug("event.received", name=event.label(), id=str(envelope.get("id", "")))

    def start ( self ) -> None:

        if self._bus.local or self._consumer is not None: return

        self._stopping.clear()
        self._consumer = asyncio.create_task(self._bus.consume(self.receive, self._stopping), name="events")

        log.info("events.listening", bus=self._bus.name)

    async def stop ( self, wait: float = 5.0 ) -> int:

        self._stopping.set()

        consumer, self._consumer = self._consumer, None

        if consumer is not None:

            try:
                async with asyncio.timeout(wait): await asyncio.shield(consumer)
            except TimeoutError: consumer.cancel()

            with contextlib.suppress(asyncio.CancelledError, Exception): await consumer

        await self._bus.close()

        return 0 if consumer is None else 1

    def pause ( self ) -> bool:

        if self._held is not None: return False

        self._held = []

        return True

    async def resume ( self ) -> int:

        held, self._held = self._held, None

        if not held: return 0

        for event in held: await self.dispatch(event)

        return len(held)

    def paused ( self ) -> bool:

        return self._held is not None

    @contextmanager
    def record ( self ) -> Iterator[list[Event]]:

        previous, self._recorded = self._recorded, []

        try: yield self._recorded
        finally: self._recorded = previous

    def history ( self, limit: int = 50 ) -> list[Envelope]:

        return list(self._history)[-limit:]

    async def replay ( self, listener: str, event: str, data: dict[str, Any] ) -> None:

        target = self._named.get(listener)

        if target is None: raise Fault(Code.INTERNAL, reason=f"listener.{listener}")

        instance = target() if isinstance(target, type) else target

        await self.call(instance, Event.of(event, data))

    async def call ( self, target: object, event: Event ) -> None:

        handle = getattr(target, "handle", None)
        bound  = handle if callable(handle) and not inspect.isfunction(target) else target
        result = bound(event) if callable(bound) else None

        if inspect.isawaitable(result): await result

    def until[E: Event] ( self, kind: type[E] ) -> asyncio.Future[E]:

        future: asyncio.Future[E] = asyncio.get_running_loop().create_future()

        self._waiting.setdefault(kind, []).append(future)

        return future

    def describe ( self ) -> dict[str, Any]:

        return {
            "bus": self._bus.name, "kinds": len(self._listeners), "listeners": sum(map(len, self._listeners.values())),
            "dispatched": self._dispatched, "paused": self.paused(), "consuming": self._consumer is not None,
        }
