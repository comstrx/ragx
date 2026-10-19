from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any
import asyncio

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
