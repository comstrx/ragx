from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token, copy_context
from typing import Any
from uuid import uuid7

from .slots import Slots
import inspect, re

type Work = Callable[[], Awaitable[Any] | Any]
type Stack = tuple[list[Work], ...]
ID      = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
CARRIED = "request_id"

async def perform ( work: Work ) -> Any:

    result = work()

    return await result if inspect.isawaitable(result) else result

class Deferral:

    __slots__ = ("_stack",)

    def __init__ ( self ) -> None:

        self._stack: ContextVar[Stack] = ContextVar("deferred", default=())

    def open ( self ) -> Token[Stack]:

        return self._stack.set((*self._stack.get(), []))

    def active ( self ) -> bool:

        return bool(self._stack.get())

    def depth ( self ) -> int:

        return len(self._stack.get())

    def pending ( self ) -> int:

        return sum(len(level) for level in self._stack.get())

    async def defer ( self, work: Work ) -> bool:

        stack = self._stack.get()

        if not stack:

            await perform(work)

            return False

        stack[-1].append(work)

        return True

    def merge ( self, token: Token[Stack] ) -> int:

        stack = self._stack.get()
        level = stack[-1] if stack else []

        self._stack.reset(token)

        parent = self._stack.get()

        if parent: parent[-1].extend(level)

        return len(level)

    def drop ( self, token: Token[Stack] ) -> int:

        stack = self._stack.get()
        level = stack[-1] if stack else []

        self._stack.reset(token)

        return len(level)

    async def flush ( self, token: Token[Stack] ) -> list[BaseException]:

        stack = self._stack.get()
        level = list(stack[-1]) if stack else []

        self._stack.reset(token)

        failures: list[BaseException] = []

        for work in level:

            try: await perform(work)
            except Exception as error: failures.append(error)

        return failures

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
    def load ( self, carried: Mapping[str, Any], fallback: str | None = None ) -> Iterator[str]:

        values = { name: value for name, value in carried.items() if name != CARRIED }

        with self.scope(carried.get(CARRIED) or fallback, **values) as request_id: yield request_id

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
