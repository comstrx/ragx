from collections.abc import Callable
from typing import Any

from core.error import Code, Fault
from .driver import Driver
from .job import DEFAULT

type Handler = Callable[..., Any]

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
