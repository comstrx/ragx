from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from core.log import log
import asyncio, contextlib

type Work = Coroutine[Any, Any, Any]
type Tick = Callable[[], Awaitable[Any] | Any]

class Tasks:

    def __init__ ( self ) -> None:

        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def spawn ( self, name: str, work: Work ) -> asyncio.Task[Any]:

        self.cancel(name)

        task = asyncio.create_task(work, name=name)

        self._tasks[name] = task
        task.add_done_callback(lambda done: self._settled_(name, done))

        return task

    def every ( self, name: str, seconds: float, tick: Tick, immediately: bool = False ) -> asyncio.Task[Any]:

        async def loop () -> None:

            if not immediately: await asyncio.sleep(seconds)

            while True:

                try:

                    result = tick()

                    if asyncio.iscoroutine(result) or isinstance(result, Awaitable): await result

                except Exception: log.exception("tasks.tick_failed", task=name)

                await asyncio.sleep(seconds)

        return self.spawn(name, loop())

    def after ( self, name: str, seconds: float, tick: Tick ) -> asyncio.Task[Any]:

        async def later () -> None:

            await asyncio.sleep(seconds)

            result = tick()

            if asyncio.iscoroutine(result) or isinstance(result, Awaitable): await result

        return self.spawn(name, later())

    def cancel ( self, name: str ) -> bool:

        task = self._tasks.pop(name, None)

        if task is None or task.done(): return False

        task.cancel()

        return True

    async def stop ( self, name: str ) -> bool:

        task = self._tasks.pop(name, None)

        if task is None: return False

        task.cancel()

        with contextlib.suppress(asyncio.CancelledError, Exception): await task

        return True

    async def stop_all ( self ) -> int:

        names = list(self._tasks)

        for name in names: await self.stop(name)

        return len(names)

    def alive ( self, name: str ) -> bool:

        task = self._tasks.get(name)

        return task is not None and not task.done()

    def names ( self ) -> list[str]:
        return sorted(name for name, task in self._tasks.items() if not task.done())

    def describe ( self ) -> dict[str, str]:

        return {
            name: "cancelled" if task.cancelled() else "done" if task.done() else "running"
            for name, task in sorted(self._tasks.items())
        }

    def _settled_ ( self, name: str, task: asyncio.Task[Any] ) -> None:

        if self._tasks.get(name) is task: self._tasks.pop(name, None)

        if task.cancelled(): return

        error = task.exception()

        if error is not None: log.error("tasks.failed", task=name, error=type(error).__name__)
