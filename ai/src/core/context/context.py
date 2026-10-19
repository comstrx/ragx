from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token, copy_context
from typing import Any
from uuid import uuid7

from .defer import Deferral, Work
from .slots import Slots
import re

ID      = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
CARRIED = "request_id"

def portable ( value: object ) -> bool:

    if value is None or isinstance(value, str | int | float | bool): return True
    if isinstance(value, list | tuple): return all(portable(item) for item in value)
    if isinstance(value, dict): return all(isinstance(key, str) and portable(item) for key, item in value.items())

    return False

class Context(Slots):

    def __init__ ( self ) -> None:

        super().__init__()

        self._request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
        self.deferred = Deferral()

    def request_id ( self ) -> str | None:

        return self._request_id.get()

    def fresh_id ( self ) -> str:

        return str(uuid7())

    def accepts ( self, incoming: str | None ) -> bool:

        return bool(incoming and ID.match(incoming))

    def start ( self, request_id: str | None = None ) -> Token[str | None]:

        return self._request_id.set(request_id if self.accepts(request_id) else self.fresh_id())

    def finish ( self, token: Token[str | None] ) -> None:

        self._request_id.reset(token)

    @contextmanager
    def scope ( self, request_id: str | None = None, **values: object ) -> Iterator[str]:

        token = self.start(request_id)

        try:

            with self.bind(**values): yield self.request_id() or ""

        finally: self.finish(token)

    def dump ( self ) -> dict[str, Any]:

        carried = { name: value for name, value in self.snapshot(hidden=True).items() if portable(value) }
        current = self.request_id()

        return { **carried, CARRIED: current } if current else carried

    @contextmanager
    def load ( self, carried: Mapping[str, Any] ) -> Iterator[str]:

        values = { name: value for name, value in carried.items() if name != CARRIED }

        with self.scope(carried.get(CARRIED), **values) as request_id: yield request_id

    async def defer ( self, work: Work ) -> bool:

        return await self.deferred.defer(work)

    def deferring ( self ) -> bool:

        return self.deferred.active()

    def isolated[T] ( self, work: Callable[[], T] ) -> T:

        return copy_context().run(work)

    def describe ( self ) -> dict[str, object]:

        return {
            "request_id": self.request_id(), "slots": self.names(), "hidden": sorted(self._hidden),
            "deferred": self.deferred.pending(),
        }
