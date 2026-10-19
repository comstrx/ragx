from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any
import inspect

type Work = Callable[[], Awaitable[Any] | Any]
type Stack = tuple[list[Work], ...]

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
