from collections.abc import Sequence
from typing import Any

from core.date import date
from core.log import log
from .check import DEGRADED, DOWN, OK, Check, Probe, Result, worst
import asyncio

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

    def clear ( self ) -> None:
        self._checks.clear()

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
