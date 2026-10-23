from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Self

from engine.error import Code, Fault
from .reply import Reply
import base64, time

CLOSED   = "closed"
OPEN     = "open"
HALF     = "half_open"
type Hook = Callable[..., Awaitable[None] | None]

@dataclass(slots=True)
class Breaker:

    name      : str = "default"
    failures  : int = 5
    reset     : float = 30.0
    clock     : Callable[[], float] = time.monotonic
    state     : str = CLOSED
    count     : int = 0
    opened_at : float = 0.0
    trips     : int = 0

    def allow ( self ) -> bool:

        if self.state == CLOSED: return True
        if self.state == OPEN and self.clock() - self.opened_at >= self.reset:

            self.state = HALF

            return True

        return self.state == HALF

    def succeed ( self ) -> None:

        self.count = 0
        self.state = CLOSED

    def fail ( self ) -> None:

        self.count += 1

        if self.state == HALF or self.count >= self.failures:

            self.state     = OPEN
            self.opened_at = self.clock()
            self.trips    += 1
            self.count     = 0

    def is_open ( self ) -> bool:

        return self.state == OPEN and not self.allow()

    def guard ( self ) -> None:

        if not self.allow(): raise Fault(Code.UNAVAILABLE, reason=f"breaker.{self.name}")

    def force_open ( self ) -> None:

        self.state     = OPEN
        self.opened_at = self.clock()

    def describe ( self ) -> dict[str, Any]:

        return { "name": self.name, "state": self.state, "count": self.count, "trips": self.trips }

@dataclass(slots=True)
class Hooks:

    before  : list[Hook]
    after   : list[Hook]
    failed  : list[Hook]

    @classmethod
    def empty ( cls ) -> Hooks:

        return cls([], [], [])

    def on_before ( self, hook: Hook ) -> None:

        self.before.append(hook)

    def on_after ( self, hook: Hook ) -> None:

        self.after.append(hook)

    def on_error ( self, hook: Hook ) -> None:

        self.failed.append(hook)

    async def fire ( self, hooks: list[Hook], *args: Any ) -> None:

        for hook in hooks:

            outcome = hook(*args)

            if outcome is not None: await outcome

type Query = Mapping[str, object]

class Fluent(ABC):

    _headers : dict[str, str]
    _breaker : Breaker | None
    hooks    : Hooks

    @abstractmethod
    async def get (
        self, url: str, params: Query | None = None, headers: Mapping[str, str] | None = None,
        wait: float | None = None,
    ) -> Reply: ...

    def with_bearer ( self, token: str ) -> Self:

        self._headers["authorization"] = f"Bearer {token}"

        return self

    def with_basic ( self, user: str, password: str ) -> Self:

        self._headers["authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

        return self

    def with_header ( self, name: str, value: str ) -> Self:

        self._headers[name.lower()] = value

        return self

    def with_breaker ( self, breaker: Breaker ) -> Self:

        self._breaker = breaker

        return self

    def on_before ( self, hook: Hook ) -> Self:

        self.hooks.on_before(hook)

        return self

    def on_after ( self, hook: Hook ) -> Self:

        self.hooks.on_after(hook)

        return self

    def on_error ( self, hook: Hook ) -> Self:

        self.hooks.on_error(hook)

        return self

    def breaker ( self ) -> Breaker | None:

        return self._breaker

    async def pages (
        self, url: str, items: str = "data", following: str = "next", limit: int = 100, params: Query | None = None,
    ) -> AsyncIterator[Any]:

        target: str | None = url
        seen = 0

        while target and seen < limit:

            reply  = (await self.get(target, params if seen == 0 else None)).raise_for_status()
            body   = reply.json()
            found  = body.get(items, []) if isinstance(body, dict) else body
            target = body.get(following) if isinstance(body, dict) else None
            seen  += 1

            for item in found or []: yield item
