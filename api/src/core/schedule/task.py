from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Self

from core.cache import cache
from core.date import date
from core.log import log
from core.queue import queue
from .cron import Cron
from .frequency import Frequency
import inspect

type Action = Callable[[], Awaitable[Any] | Any]
type Hook = Callable[["Task"], Awaitable[Any] | Any]
type Test = Callable[[], Awaitable[bool] | bool]

LOCK_TTL = 3600.0

class Task(Frequency):

    def __init__ ( self, action: Action, name: str ) -> None:

        super().__init__()

        self.name      = name
        self.action    = action
        self.note      = ""
        self.exclusive = False
        self.one_server = False
        self.lock_ttl  = LOCK_TTL
        self.via_queue = False
        self.paused    = False
        self.running   = False
        self.runs      = 0
        self.failures  = 0
        self.skipped   = 0
        self.started: datetime | None = None
        self.finished: datetime | None = None
        self.last_error: str | None = None
        self.tests: list[Test] = []
        self.hooks: dict[str, list[Hook]] = { "before": [], "after": [], "success": [], "failure": [] }

    def named ( self, name: str ) -> Self:

        self.name = name

        return self

    def description ( self, text: str ) -> Self:

        self.note = text

        return self

    def without_overlapping ( self, lock_ttl: float = LOCK_TTL ) -> Self:

        self.exclusive = True
        self.lock_ttl  = lock_ttl

        return self

    def on_one_server ( self, lock_ttl: float = LOCK_TTL ) -> Self:

        self.one_server = True
        self.lock_ttl   = lock_ttl

        return self

    def queued ( self ) -> Self:

        self.via_queue = True

        return self

    def between ( self, start: str, end: str ) -> Self:

        return self.when(lambda: self.inside(start, end))

    def unless_between ( self, start: str, end: str ) -> Self:

        return self.when(lambda: not self.inside(start, end))

    def inside ( self, start: str, end: str ) -> bool:

        now  = date.now().astimezone(self.zone)
        low  = self.clock(start)
        high = self.clock(end)
        here = (now.hour, now.minute)

        return low <= here <= high if low <= high else here >= low or here <= high

    def last_day_of_month ( self, clock: str = "00:00" ) -> Self:

        hour, minute = self.clock(clock)

        return self.at(f"{minute} {hour} 28-31 * *").when(lambda: date.moment(None, self.zone).is_last_of_month())

    def when ( self, test: Test ) -> Self:

        self.tests.append(test)

        return self

    def skip ( self, test: Test ) -> Self:

        async def inverted () -> bool:

            result = test()

            return not (await result if inspect.isawaitable(result) else result)

        return self.when(inverted)

    def before ( self, hook: Hook ) -> Self:

        return self.hook("before", hook)

    def after ( self, hook: Hook ) -> Self:

        return self.hook("after", hook)

    def on_success ( self, hook: Hook ) -> Self:

        return self.hook("success", hook)

    def on_failure ( self, hook: Hook ) -> Self:

        return self.hook("failure", hook)

    def hook ( self, stage: str, hook: Hook ) -> Self:

        self.hooks[stage].append(hook)

        return self

    def pause ( self ) -> Self:

        self.paused = True

        return self

    def resume ( self ) -> Self:

        self.paused = False

        return self

    def due ( self, now: datetime ) -> bool:

        if self.paused or (self.exclusive and self.running): return False
        if self.interval is not None:
            return self.started is None or (now - self.started).total_seconds() >= self.interval

        return self.cron is not None and self.due_cron(self.cron, now.astimezone(self.zone))

    def due_cron ( self, cron: Cron, local: datetime ) -> bool:

        if not cron.matches(local): return False
        if self.started is None: return True

        last = self.started.astimezone(self.zone).replace(second=0, microsecond=0)

        return last != local.replace(second=0, microsecond=0)

    def next_run ( self, now: datetime | None = None ) -> datetime | None:

        moment = now or date.now()

        if self.interval is not None:
            return moment if self.started is None else self.started + date.duration(self.interval).timedelta()

        return self.cron.next(moment.astimezone(self.zone)) if self.cron is not None else None

    async def allowed ( self ) -> bool:

        for test in self.tests:

            result = test()

            if not (await result if inspect.isawaitable(result) else result): return False

        return True

    async def run ( self ) -> bool:

        if not await self.allowed():

            self.skipped += 1

            return False

        lock = cache.lock(f"schedule:{self.name}", self.lock_ttl) if self.one_server else None

        if lock is not None and not await lock.acquire():

            self.skipped += 1

            return False

        try: return await self.execute()
        finally:
            if lock is not None: await lock.release()

    async def execute ( self ) -> bool:

        self.running = True
        self.started = date.now()

        await self.fire("before")

        try:

            if self.via_queue and not queue.inline(): await queue.push(self.action)
            else:

                result = self.action()

                if inspect.isawaitable(result): await result

        except Exception as error:

            self.failures  += 1
            self.last_error = type(error).__name__

            log.exception("schedule.failed", task=self.name)

            await self.fire("failure")

            return False

        finally:

            self.running  = False
            self.finished = date.now()

            await self.fire("after")

        self.runs += 1

        await self.fire("success")

        return True

    async def fire ( self, stage: str ) -> None:

        for hook in self.hooks[stage]:

            result = hook(self)

            if inspect.isawaitable(result): await result

    def dump ( self ) -> dict[str, Any]:

        return {
            "name"     : self.name,
            "note"     : self.note,
            "cron"     : self.cron.expression if self.cron else None,
            "every"    : self.interval,
            "zone"     : str(self.zone),
            "paused"   : self.paused,
            "runs"     : self.runs,
            "failures" : self.failures,
            "skipped"  : self.skipped,
            "running"  : self.running,
            "started"  : date.iso(self.started) if self.started else None,
            "finished" : date.iso(self.finished) if self.finished else None,
            "error"    : self.last_error,
        }
