from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any

from core.log import log
from .run import Run
from .tasks import Tasks
import asyncio, contextlib, signal

type Hook = Callable[[], Awaitable[None] | None]
SIGNALS = (signal.SIGTERM, signal.SIGINT)

class Lane:

    def __init__ ( self, limit: int ) -> None:

        self._gate  = asyncio.Semaphore(max(limit, 1))
        self._limit = max(limit, 1)
        self._busy  = 0
        self._peak  = 0

    @asynccontextmanager
    async def slot ( self ) -> AsyncIterator[None]:

        async with self._gate:

            self._busy += 1
            self._peak  = max(self._peak, self._busy)

            try: yield
            finally: self._busy -= 1

    async def run[T] ( self, job: Awaitable[T] ) -> T:

        async with self.slot(): return await job

    async def map[T, R] ( self, fn: Callable[[T], Awaitable[R]], items: Iterable[T] ) -> list[R]:

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self.run(fn(item))) for item in items]

        return [task.result() for task in tasks]

    def busy ( self ) -> int:

        return self._busy

    def free ( self ) -> int:

        return self._limit - self._busy

    def describe ( self ) -> dict[str, int]:

        return { "limit": self._limit, "busy": self._busy, "peak": self._peak }

class Pool:

    def __init__ ( self ) -> None:

        self._lanes: dict[str, Lane] = {}

    def lane ( self, name: str, limit: int = 8 ) -> Lane:

        found = self._lanes.get(name)

        if found is None: found = self._lanes[name] = Lane(limit)

        return found

    async def within[T] ( self, name: str, job: Awaitable[T], limit: int = 8 ) -> T:

        return await self.lane(name, limit).run(job)

    def describe ( self ) -> dict[str, Any]:

        return { name: lane.describe() for name, lane in sorted(self._lanes.items()) }

    def forget ( self, name: str ) -> bool:

        return self._lanes.pop(name, None) is not None

class Shutdown:

    def __init__ ( self ) -> None:

        self._event: asyncio.Event | None = None
        self._hooks: list[Hook] = []
        self._installed = False
        self._reason    = ""

    def event ( self ) -> asyncio.Event:

        if self._event is None: self._event = asyncio.Event()

        return self._event

    def install ( self ) -> bool:

        if self._installed: return False

        loop = asyncio.get_running_loop()

        for sig in SIGNALS:

            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.trigger, sig.name)

        self._installed = True

        return True

    def on ( self, hook: Hook ) -> None:

        if hook not in self._hooks: self._hooks.append(hook)

    def trigger ( self, reason: str = "requested" ) -> None:

        if self.event().is_set(): return

        self._reason = reason

        log.info("shutdown.triggered", reason=reason)
        self.event().set()

    def triggered ( self ) -> bool:

        return self._event is not None and self._event.is_set()

    def reason ( self ) -> str:

        return self._reason

    async def wait ( self ) -> str:

        await self.event().wait()

        return self._reason

    async def drain ( self, wait: float = 10.0 ) -> int:

        done = 0

        for hook in reversed(self._hooks):

            try:

                async with asyncio.timeout(wait):

                    result = hook()

                    if result is not None: await result

                done += 1

            except Exception: log.exception("shutdown.hook_failed", hook=getattr(hook, "__qualname__", "hook"))

        return done

    def reset ( self ) -> None:

        self._event     = None
        self._hooks     = []
        self._installed = False
        self._reason    = ""

class Thread(Run):

    def __init__ ( self ) -> None:

        self.pool     = Pool()
        self.tasks    = Tasks()
        self.shutdown = Shutdown()

    def lane ( self, name: str, limit: int = 8 ) -> Lane:

        return self.pool.lane(name, limit)

    def describe ( self ) -> dict[str, object]:

        return {
            "lanes": self.pool.describe(),
            "tasks": self.tasks.describe(),
            "shutdown": self.shutdown.triggered(),
        }
