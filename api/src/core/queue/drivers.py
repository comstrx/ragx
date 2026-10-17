from core.date import date
from .queue import Job
import asyncio, heapq, itertools

class MemoryDriver:

    name = "memory"

    def __init__ ( self ) -> None:

        self._heaps: dict[str, list[tuple[float, int, Job]]] = {}
        self._wakeups: dict[str, asyncio.Event] = {}
        self._order = itertools.count()

    def _heap_ ( self, queue: str ) -> list[tuple[float, int, Job]]:
        return self._heaps.setdefault(queue, [])

    def _wakeup_ ( self, queue: str ) -> asyncio.Event:
        return self._wakeups.setdefault(queue, asyncio.Event())

    async def push ( self, job: Job ) -> None:

        heapq.heappush(self._heap_(job.queue), (job.available, next(self._order), job))

        self._wakeup_(job.queue).set()

    async def pull ( self, queue: str, wait: float ) -> Job | None:

        heap     = self._heap_(queue)
        deadline = date.stamp() + wait

        while True:

            now = date.stamp()

            if heap and heap[0][0] <= now: return heapq.heappop(heap)[2]

            remaining = deadline - now

            if remaining <= 0: return None

            pause = min(remaining, heap[0][0] - now) if heap else remaining
            flag  = self._wakeup_(queue)

            flag.clear()

            try:
                async with asyncio.timeout(max(pause, 0.001)): await flag.wait()
            except TimeoutError: continue

    async def size ( self, queue: str ) -> int:
        return len(self._heap_(queue))

    async def clear ( self, queue: str ) -> int:

        count = len(self._heap_(queue))

        self._heap_(queue).clear()

        return count

class SyncDriver:

    name = "sync"

    async def push ( self, _job: Job ) -> None:
        return None

    async def pull ( self, _queue: str, _wait: float ) -> Job | None:
        return None

    async def size ( self, _queue: str ) -> int:
        return 0

    async def clear ( self, _queue: str ) -> int:
        return 0
