from collections.abc import Awaitable, Callable, Sequence

from core.error import Fault
from core.log import log
from .job import Job
import asyncio, contextlib

type Pull = Callable[[str, float], Awaitable[Job | None]]
type Perform = Callable[[Job], Awaitable[bool]]

PULL = 0.5
CALM = 5.0

class Workers:

    def __init__ ( self, pull: Pull, perform: Perform ) -> None:

        self._pull    = pull
        self._perform = perform
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        self._running  = asyncio.Event()
        self._busy     = 0
        self._stalls   = 0

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

        streak = 0

        while not self._stopping.is_set():

            await self._running.wait()

            if self._stopping.is_set(): return

            try:

                await self.turn(queue)

                streak = 0

            except Fault as fault:

                streak       += 1
                self._stalls += 1

                self.stalled(queue, fault, streak)

                await self.rest(min(PULL * 2.0 ** streak, CALM))

    async def turn ( self, queue: str ) -> None:

        job = await self.next(queue)

        if job is None: return

        self._busy += 1

        try: await self._perform(job)
        finally: self._busy -= 1

    def stalled ( self, queue: str, fault: Fault, streak: int ) -> None:

        if fault.code.transient(): log.warning("queue.worker.stalled", queue=queue, streak=streak, reason=fault.reason)
        else: log.exception("queue.worker.faulted", queue=queue, streak=streak, reason=fault.reason)

    async def rest ( self, pause: float ) -> None:

        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(pause): await self._stopping.wait()

    async def next ( self, queue: str ) -> Job | None:

        pull = asyncio.ensure_future(self._pull(queue, PULL))
        halt = asyncio.ensure_future(self._stopping.wait())

        done, _ = await asyncio.wait({ pull, halt }, return_when=asyncio.FIRST_COMPLETED)

        if pull in done:

            halt.cancel()

            return pull.result()

        pull.cancel()

        with contextlib.suppress(asyncio.CancelledError): await pull

        return None

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

        return { "workers": self.alive(), "busy": self._busy, "paused": self.paused(), "stalls": self._stalls }

    def warn_if_dead ( self ) -> None:

        dead = [task.get_name() for task in self._tasks if task.done() and not task.cancelled()]

        if dead: log.warning("queue.workers_dead", workers=dead)
