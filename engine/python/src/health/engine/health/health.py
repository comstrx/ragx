from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Self

from engine.cache import cache
from engine.database import Database
from engine.date import date
from engine.error import Code, Fault
from engine.event import events
from engine.http import Facts, Request, Response, Route
from engine.llm import llm
from engine.log import log
from engine.queue import queue
from engine.storage import storage
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

class Health:

    def __init__ ( self ) -> None:

        self._checks: dict[str, Check] = {}
        self._last: dict[str, Any] | None = None

    def register (
        self, name: str, probe: Probe, critical: bool = True, wait: float = 3.0, tags: Sequence[str] = (),
    ) -> Check:

        check = Check(name, probe, critical, wait, tuple(tags))

        self._checks[name] = check

        return check

    def forget ( self, name: str ) -> bool:

        return self._checks.pop(name, None) is not None

    def names ( self ) -> list[str]:

        return sorted(self._checks)

    def has ( self, name: str ) -> bool:

        return name in self._checks

    def clear ( self ) -> int:

        count = len(self._checks)

        self._checks.clear()

        return count

    async def run ( self, name: str ) -> Result:

        check = self._checks[name]
        result, _ = await check.run()

        return result

    async def report ( self, only: Sequence[str] = (), tag: str | None = None ) -> dict[str, Any]:

        chosen  = [
            check for check in self._checks.values()
            if (not only or check.name in only) and (tag is None or tag in check.tags)
        ]
        started = date.tick()
        ran     = await asyncio.gather(*(check.run() for check in chosen))
        checks  = {
            check.name: { **result.dump(), "ms": ms, "critical": check.critical }
            for check, (result, ms) in zip(chosen, ran, strict=True)
        }
        status  = self.verdict(chosen, [result for result, _ in ran])
        report  = { "status": status, "checks": checks, "ms": date.elapsed(started), "at": date.iso(date.now()) }

        self._last = report

        if status != OK: log.warning("health.degraded", status=status, failing=self.failing(report))

        return report

    def verdict ( self, checks: list[Check], results: list[Result] ) -> str:

        statuses = [
            result.status if check.critical or result.status != DOWN else DEGRADED
            for check, result in zip(checks, results, strict=True)
        ]

        return worst(statuses)

    def failing ( self, report: dict[str, Any] ) -> list[str]:

        return sorted(name for name, check in report["checks"].items() if check["status"] != OK)

    async def healthy ( self, only: Sequence[str] = () ) -> bool:

        return str((await self.report(only))["status"]) == OK

    async def alive ( self ) -> bool:

        return str((await self.report(tag="live"))["status"]) != DOWN

    async def ready ( self ) -> bool:

        return str((await self.report(tag="ready"))["status"]) == OK

    def last ( self ) -> dict[str, Any] | None:

        return self._last

    def describe ( self ) -> dict[str, Any]:

        return {
            "checks": [
                { "name": check.name, "critical": check.critical, "tags": list(check.tags) }
                for check in self._checks.values()
            ],
            "last": self._last["status"] if self._last else None,
        }

class Heartbeat:

    def __init__ ( self, health: Health, database: Database ) -> None:

        self._health   = health
        self._database = database

    def register ( self ) -> int:

        self._health.register("database", self.database, tags=("ready", "live"))
        self._health.register("cache", self.cache, critical=False, tags=("ready",))
        self._health.register("queue", self.queue, critical=False, tags=("ready",))
        self._health.register("events", lambda: Result.ok(**events.describe()), critical=False)
        self._health.register("storage", lambda: Result.ok(**storage.describe()), critical=False)
        self._health.register("llm", lambda: Result.ok(**llm.describe()), critical=False)

        return len(self._health.names())

    def route ( self ) -> Route:

        return Route.get("/health", self.index, name="health", tags=("health",))

    async def database ( self ) -> Result:

        alive = await self._database.ping()

        return Result.ok(alive=True, **self._database.describe()) if alive else Result.down("database", alive=False)

    async def cache ( self ) -> Result:

        pinger = getattr(cache.store(), "ping", None)
        alive  = await pinger() if callable(pinger) else True

        return Result.ok(**cache.describe()) if alive else Result.degraded("cache", **cache.describe())

    async def queue ( self ) -> Result:

        return Result.ok(**queue.describe()) if queue.ready() else Result.degraded("queue")

    async def index ( self, request: Request ) -> Response:

        facts  = Facts.of(request)
        report = await self._health.report()
        status = {
            "status"   : report["status"],
            "version"  : facts.get("version"),
            "release"  : facts.get("release"),
            "database" : report["checks"]["database"],
            "checks"   : report["checks"],
            "ms"       : report["ms"],
        }

        if report["checks"]["database"]["status"] != "ok":

            return Response.fail(Fault(Code.UNAVAILABLE, reason="database"), meta={ "health": status })

        return Response.ok(status)
