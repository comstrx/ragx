from collections.abc import Awaitable, Callable, Sequence

from core.log import log
from .job import Job
import asyncio

type Pull = Callable[[str, float], Awaitable[Job | None]]
type Perform = Callable[[Job], Awaitable[bool]]

PULL = 0.5

class Workers:

    def __init__ ( self, pull: Pull, perform: Perform ) -> None:

        self._pull    = pull
        self._perform = perform
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        self._running  = asyncio.Event()
        self._busy     = 0

        self._running.set()

    def start ( self, queues: Sequence[str], count: int = 1 ) -> int:

        if self._tasks or count < 1: return 0

        self._stopping.clear()
        self._running.set()

        for queue in queues:
            for index in range(count):
                self._tasks.append(asyncio.create_task(self.work(queue), name=f"queue:{queue}:{index}"))

        return len(self._tasks)

    async def work ( self, queue: str ) -> None:

        while not self._stopping.is_set():

            await self._running.wait()

            if self._stopping.is_set(): return

            job = await self._pull(queue, PULL)

            if job is None: continue

            self._busy += 1

            try: await self._perform(job)
            finally: self._busy -= 1

    def pause ( self ) -> bool:

        if not self._running.is_set(): return False

        self._running.clear()

        return True

    def resume ( self ) -> bool:

        if self._running.is_set(): return False

        self._running.set()

        return True

    def paused ( self ) -> bool:
        return bool(self._tasks) and not self._running.is_set()

    async def stop ( self, wait: float = 5.0 ) -> int:

        if not self._tasks: return 0

        self._stopping.set()
        self._running.set()

        try:
            async with asyncio.timeout(wait): await asyncio.gather(*self._tasks, return_exceptions=True)
        except TimeoutError:
            for task in self._tasks: task.cancel()

        stopped = len(self._tasks)

        self._tasks.clear()

        return stopped

    def alive ( self ) -> int:
        return sum(1 for task in self._tasks if not task.done())

    def busy ( self ) -> int:
        return self._busy

    def names ( self ) -> list[str]:
        return [task.get_name() for task in self._tasks if not task.done()]

    def describe ( self ) -> dict[str, object]:
        return { "workers": self.alive(), "busy": self._busy, "paused": self.paused() }

    def warn_if_dead ( self ) -> None:

        dead = [task.get_name() for task in self._tasks if task.done() and not task.cancelled()]

        if dead: log.warning("queue.workers_dead", workers=dead)
