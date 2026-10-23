from datetime import datetime
from typing import Any

from engine.date import date
from engine.error import Code, Fault
from engine.log import log
from .task import Action, Task
import asyncio, contextlib

TICK = 1.0

class Schedule:

    def __init__ ( self ) -> None:

        self._tasks: list[Task] = []
        self._ticker: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._ticks    = 0

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

    def names ( self ) -> list[str]:

        return [task.name for task in self._tasks]

    def find ( self, name: str ) -> Task:

        found = next((task for task in self._tasks if task.name == name), None)

        if found is None: raise Fault(Code.NOT_FOUND, reason=f"schedule.{name}")

        return found

    def has ( self, name: str ) -> bool:

        return any(task.name == name for task in self._tasks)

    def forget ( self, name: str ) -> bool:

        before = len(self._tasks)

        self._tasks = [task for task in self._tasks if task.name != name]

        return len(self._tasks) < before

    def clear ( self ) -> int:

        count = len(self._tasks)

        self._tasks.clear()

        return count

    def pause ( self, name: str | None = None ) -> int:

        chosen = [self.find(name)] if name else self._tasks

        for task in chosen: task.pause()

        return len(chosen)

    def resume ( self, name: str | None = None ) -> int:

        chosen = [self.find(name)] if name else self._tasks

        for task in chosen: task.resume()

        return len(chosen)

    def due ( self, now: datetime | None = None ) -> list[Task]:

        moment = now or date.now()

        return [task for task in self._tasks if task.due(moment)]

    async def run_due ( self, now: datetime | None = None ) -> list[str]:

        ready = self.due(now)

        if ready: await asyncio.gather(*(task.run() for task in ready), return_exceptions=True)

        self._ticks += 1

        return [task.name for task in ready]

    async def run ( self, name: str ) -> bool:

        return await self.find(name).execute()

    def upcoming ( self, count: int = 10, now: datetime | None = None ) -> list[dict[str, Any]]:

        moment = now or date.now()
        slots  = [(task.next_run(moment), task.name) for task in self._tasks if not task.paused]
        known  = sorted((when, name) for when, name in slots if when is not None)

        return [{ "at": date.iso(when), "task": name } for when, name in known[:count]]

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

    async def stop ( self, wait: float = 5.0 ) -> int:

        ticker, self._ticker = self._ticker, None

        if ticker is None: return 0

        self._stopping.set()

        try:
            async with asyncio.timeout(wait): await asyncio.shield(ticker)
        except TimeoutError: ticker.cancel()

        with contextlib.suppress(asyncio.CancelledError, Exception): await ticker

        log.info("schedule.stopped", ticks=self._ticks)

        return 1

    def running ( self ) -> bool:

        return self._ticker is not None and not self._ticker.done()

    def status ( self ) -> list[dict[str, Any]]:

        return [task.dump() for task in self._tasks]

    def describe ( self ) -> dict[str, Any]:

        return {
            "running": self.running(), "tasks": len(self._tasks), "paused": sum(task.paused for task in self._tasks),
            "ticks": self._ticks, "upcoming": self.upcoming(3),
        }
