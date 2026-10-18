from typing import Protocol

from core.date import date
from .job import Job
import asyncio, heapq, itertools

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    async def push ( self, job: Job ) -> None: ...

    async def pull ( self, queue: str, wait: float ) -> Job | None: ...

    async def size ( self, queue: str ) -> int: ...

    async def clear ( self, queue: str ) -> int: ...

    async def ack ( self, job: Job ) -> None: ...

    async def close ( self ) -> None: ...

class MemoryDriver:

    name = "memory"

    def __init__ ( self ) -> None:

        self._heaps: dict[str, list[tuple[float, int, Job]]] = {}
        self._wakeups: dict[str, asyncio.Event] = {}
        self._order = itertools.count()

    def heap ( self, queue: str ) -> list[tuple[float, int, Job]]:
        return self._heaps.setdefault(queue, [])

    def wakeup ( self, queue: str ) -> asyncio.Event:
        return self._wakeups.setdefault(queue, asyncio.Event())

    async def push ( self, job: Job ) -> None:

        heapq.heappush(self.heap(job.queue), (job.available, next(self._order), job))

        self.wakeup(job.queue).set()

    async def pull ( self, queue: str, wait: float ) -> Job | None:

        heap     = self.heap(queue)
        deadline = date.stamp() + wait

        while True:

            now = date.stamp()

            if heap and heap[0][0] <= now: return heapq.heappop(heap)[2]

            remaining = deadline - now

            if remaining <= 0: return None

            pause = min(remaining, heap[0][0] - now) if heap else remaining
            flag  = self.wakeup(queue)

            flag.clear()

            try:
                async with asyncio.timeout(max(pause, 0.001)): await flag.wait()
            except TimeoutError: continue

    async def size ( self, queue: str ) -> int:
        return len(self.heap(queue))

    async def clear ( self, queue: str ) -> int:

        count = len(self.heap(queue))

        self.heap(queue).clear()

        return count

    async def ack ( self, _job: Job ) -> None:
        return None

    async def close ( self ) -> None:
        return None

    def peek ( self, queue: str, limit: int = 20 ) -> list[Job]:
        return [entry[2] for entry in heapq.nsmallest(limit, self.heap(queue))]

    def queues ( self ) -> list[str]:
        return sorted(name for name, heap in self._heaps.items() if heap)

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

    async def ack ( self, _job: Job ) -> None:
        return None

    async def close ( self ) -> None:
        return None
