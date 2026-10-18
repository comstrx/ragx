from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from core.date import date
import asyncio, inspect

type Verdict = bool | str | Mapping[str, Any] | "Result"
type Probe = Callable[[], Awaitable[Verdict] | Verdict]

OK       = "ok"
DEGRADED = "degraded"
DOWN     = "down"
RANKS    = { OK: 0, DEGRADED: 1, DOWN: 2 }

@dataclass(frozen=True, slots=True)
class Result:

    status : str = OK
    facts  : Mapping[str, Any] = field(default_factory=dict)
    reason : str | None = None

    @classmethod
    def ok ( cls, **facts: Any ) -> Self:
        return cls(OK, facts)

    @classmethod
    def degraded ( cls, reason: str | None = None, **facts: Any ) -> Self:
        return cls(DEGRADED, facts, reason)

    @classmethod
    def down ( cls, reason: str | None = None, **facts: Any ) -> Self:
        return cls(DOWN, facts, reason)

    @classmethod
    def of ( cls, verdict: Any ) -> Result:

        if isinstance(verdict, Result): return verdict
        if isinstance(verdict, bool): return cls(OK if verdict else DOWN)
        if isinstance(verdict, str): return cls(verdict, {}, None) if verdict in RANKS else cls(DOWN, {}, verdict)
        if isinstance(verdict, Mapping):

            status = str(verdict.get("status", OK))

            return cls(status if status in RANKS else DEGRADED, dict(verdict), verdict.get("reason"))

        return cls(OK)

    def healthy ( self ) -> bool:
        return self.status == OK

    def dump ( self ) -> dict[str, Any]:

        body: dict[str, Any] = { "status": self.status, **self.facts }

        if self.reason: body["reason"] = self.reason

        return body

@dataclass(slots=True)
class Check:

    name     : str
    probe    : Probe
    critical : bool = True
    wait     : float = 3.0
    tags     : tuple[str, ...] = ()

    async def run ( self ) -> tuple[Result, float]:

        started = date.tick()

        try:

            outcome = self.probe()

            if inspect.isawaitable(outcome): outcome = await asyncio.wait_for(outcome, self.wait)

            result = Result.of(outcome)

        except TimeoutError: result = Result.down("timeout")
        except Exception as error: result = Result.down(type(error).__name__)

        return result, date.elapsed(started)

def worst ( statuses: list[str] ) -> str:
    return max(statuses, key=lambda status: RANKS.get(status, 2)) if statuses else OK
