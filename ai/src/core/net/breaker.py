from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from core.error import Code, Fault
import time

CLOSED   = "closed"
OPEN     = "open"
HALF     = "half_open"

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

type Hook = Callable[..., Awaitable[None] | None]

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
