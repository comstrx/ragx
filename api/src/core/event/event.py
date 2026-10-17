from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, ClassVar, Protocol, Self

from core.exceptions import Code, Fault
from core.json import json
from core.log import log
from core.queue import Queued, queue
import asyncio, inspect

type Handler = Callable[[Any], Awaitable[None] | None]
type Target = Handler | type[Listener] | Listener

class Event:

    registry : ClassVar[dict[str, type[Event]]] = {}
    kind     : ClassVar[str] = ""

    def __init_subclass__ ( cls, **kwargs: object ) -> None:

        super().__init_subclass__(**kwargs)

        cls.kind = f"{cls.__module__}:{cls.__qualname__}"

        Event.registry[cls.kind] = cls

    def dump ( self ) -> dict[str, Any]:

        data: Any = asdict(self) if is_dataclass(self) else dict(vars(self))
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

    def channels ( self ) -> Sequence[str]:
        return ()

    def payload ( self ) -> dict[str, Any]:
        return self.dump()

    def label ( self ) -> str:
        return type(self).__name__

class Listener(Protocol):

    async def handle ( self, event: Any ) -> None: ...

class Events:

    def __init__ ( self ) -> None:

        self._listeners: dict[type[Event], list[Target]] = {}
        self._named: dict[str, Target] = {}
        self._any: list[Handler] = []
        self._waiting: dict[type[Event], list[asyncio.Future[Any]]] = {}

    def listen ( self, kind: type[Event], *targets: Target ) -> Self:

        group = self._listeners.setdefault(kind, [])

        for target in targets:

            if target not in group: group.append(target)

            self._named[self.name_of(target)] = target

        return self

    def subscribe ( self, mapping: Mapping[type[Any], Sequence[Any]] ) -> Self:

        for kind, targets in mapping.items(): self.listen(kind, *targets)

        return self

    def on_any ( self, handler: Handler ) -> Self:

        if handler not in self._any: self._any.append(handler)

        return self

    def forget ( self, kind: type[Event] ) -> None:
        self._listeners.pop(kind, None)

    def listeners ( self, kind: type[Event] ) -> list[Target]:
        return [target for known, group in self._listeners.items() if issubclass(kind, known) for target in group]

    def name_of ( self, target: Target ) -> str:

        kind = target if isinstance(target, type) else (target if inspect.isfunction(target) else type(target))

        return f"{kind.__module__}:{kind.__qualname__}"

    async def dispatch ( self, event: Event ) -> int:

        targets = self.listeners(type(event))

        for target in targets: await self.deliver(target, event)
        for handler in self._any: await self.call(handler, event)

        for future in self._waiting.pop(type(event), []):
            if not future.done(): future.set_result(event)

        log.debug("event.dispatched", name=event.label(), listeners=len(targets))

        return len(targets)

    async def deliver ( self, target: Target, event: Event ) -> None:

        instance = target() if isinstance(target, type) else target

        if isinstance(instance, Queued) and not queue.inline():

            await queue.push(
                self.replay, self.name_of(target), event.kind, event.dump(),
                queue=instance.queue, delay=instance.delay, tries=instance.tries, backoff=instance.backoff,
            )

            return

        await self.call(instance, event)

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
