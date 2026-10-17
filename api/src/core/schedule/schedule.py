from collections.abc import Awaitable, Callable
from datetime import datetime, tzinfo
from typing import Any, Self
from zoneinfo import ZoneInfo

from core.date import date
from core.exceptions import Code, Fault
from core.log import log
from core.queue import queue
from .cron import Cron
import asyncio, inspect

type Action = Callable[[], Awaitable[Any] | Any]

MINUTE = 60.0
HOUR   = 3600.0
DAY    = 86400.0
TICK   = 1.0
WEEK   = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")

class Task:

    def __init__ ( self, action: Action, name: str ) -> None:

        self.name     = name
        self.action   = action
        self.cron: Cron | None = None
        self.interval: float | None = None
        self.exclusive = False
        self.zone: tzinfo = ZoneInfo("UTC")
        self.via_queue = False
        self.running   = False
        self.runs      = 0
        self.failures  = 0
        self.started: datetime | None = None
        self.finished: datetime | None = None

    def named ( self, name: str ) -> Self:

        self.name = name

        return self

    def at ( self, expression: str ) -> Self:

        self.cron     = Cron(expression)
        self.interval = None

        return self

    def every ( self, seconds: float ) -> Self:

        if seconds <= 0: raise Fault(Code.INTERNAL, reason="schedule.interval")

        self.interval = float(seconds)
        self.cron     = None

        return self

    def every_minute ( self ) -> Self:
        return self.at("* * * * *")

    def every_minutes ( self, count: int ) -> Self:
        return self.at(f"*/{count} * * * *")

    def hourly ( self, minute: int = 0 ) -> Self:
        return self.at(f"{minute} * * * *")

    def daily ( self ) -> Self:
        return self.at("0 0 * * *")

    def daily_at ( self, clock: str ) -> Self:

        hour, minute = self.clock(clock)

        return self.at(f"{minute} {hour} * * *")

    def weekly_on ( self, day: str | int, clock: str = "00:00" ) -> Self:

        hour, minute = self.clock(clock)
        index        = WEEK.index(day.lower()) if isinstance(day, str) else day

        return self.at(f"{minute} {hour} * * {index}")

    def monthly_on ( self, day: int, clock: str = "00:00" ) -> Self:

        hour, minute = self.clock(clock)

        return self.at(f"{minute} {hour} {day} * *")

    def clock ( self, text: str ) -> tuple[int, int]:

        hour, _, minute = text.partition(":")

        return int(hour), int(minute or 0)

    def timezone ( self, name: str ) -> Self:

        self.zone = ZoneInfo(name)

        return self

    def without_overlapping ( self ) -> Self:

        self.exclusive = True

        return self

    def queued ( self ) -> Self:

        self.via_queue = True

        return self

    def due ( self, now: datetime ) -> bool:

        if self.exclusive and self.running: return False
        if self.interval is not None:
            return self.started is None or (now - self.started).total_seconds() >= self.interval

        return self.cron is not None and self.due_cron(self.cron, now.astimezone(self.zone))

    def due_cron ( self, cron: Cron, local: datetime ) -> bool:

        if not cron.matches(local): return False
        if self.started is None: return True

        last = self.started.astimezone(self.zone).replace(second=0, microsecond=0)

        return last != local.replace(second=0, microsecond=0)

    async def run ( self ) -> bool:

        self.running = True
        self.started = date.now()

        try:

            if self.via_queue and not queue.inline(): await queue.push(self.action)
            else:

                result = self.action()

                if inspect.isawaitable(result): await result

        except Exception:

            self.failures += 1

            log.exception("schedule.failed", task=self.name)

            return False

        finally:

            self.running  = False
            self.finished = date.now()

        self.runs += 1

        return True

    def dump ( self ) -> dict[str, Any]:

        return {
            "name"     : self.name,
            "cron"     : self.cron.expression if self.cron else None,
            "every"    : self.interval,
            "zone"     : str(self.zone),
            "runs"     : self.runs,
            "failures" : self.failures,
            "running"  : self.running,
            "started"  : date.iso(self.started) if self.started else None,
            "finished" : date.iso(self.finished) if self.finished else None,
        }

class Schedule:

    def __init__ ( self ) -> None:

        self._tasks: list[Task] = []
        self._ticker: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def call ( self, action: Action, name: str | None = None ) -> Task:

        task = Task(action, name or f"{action.__module__}:{action.__qualname__}")

        self._tasks.append(task)

        return task

    def job ( self, dispatchable: Any, name: str | None = None ) -> Task:

        dispatch = getattr(dispatchable, "dispatch", None)
        label    = name or getattr(dispatchable, "__name__", type(dispatchable).__name__)

        return self.call(dispatch if callable(dispatch) else dispatchable, label)

    def tasks ( self ) -> list[Task]:
        return list(self._tasks)

    def find ( self, name: str ) -> Task:

        found = next((task for task in self._tasks if task.name == name), None)

        if found is None: raise Fault(Code.NOT_FOUND, reason=f"schedule.{name}")

        return found

    def clear ( self ) -> None:
        self._tasks.clear()

    def due ( self, now: datetime | None = None ) -> list[Task]:

        moment = now or date.now()

        return [task for task in self._tasks if task.due(moment)]

    async def run_due ( self, now: datetime | None = None ) -> list[str]:

        ready = self.due(now)

        if ready: await asyncio.gather(*(task.run() for task in ready))

        return [task.name for task in ready]

    def start ( self, tick: float = TICK ) -> None:

        if self._ticker is not None: return

        self._stopping.clear()
        self._ticker = asyncio.create_task(self.loop(tick), name="schedule")

        log.info("schedule.started", tasks=len(self._tasks), tick=tick)

    async def loop ( self, tick: float ) -> None:

        while not self._stopping.is_set():

            await self.run_due()

            try:
                async with asyncio.timeout(tick): await self._stopping.wait()
            except TimeoutError: continue

    async def stop ( self ) -> None:

        if self._ticker is None: return

        self._stopping.set()

        await self._ticker

        self._ticker = None

        log.info("schedule.stopped")

    def status ( self ) -> list[dict[str, Any]]:
        return [task.dump() for task in self._tasks]
