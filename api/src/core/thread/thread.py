from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
import asyncio, functools

type Job[T] = Callable[[], Awaitable[T]]
type Task[T] = Coroutine[Any, Any, T]

class Thread:

    async def gather[T] ( self, *jobs: Awaitable[T], limit: int = 0 ) -> list[T]:

        gate = asyncio.Semaphore(limit) if limit > 0 else None

        async def one ( job: Awaitable[T] ) -> T:

            if gate is None: return await job

            async with gate: return await job

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(job)) for job in jobs]

        return [task.result() for task in tasks]

    async def timeout[T] ( self, job: Awaitable[T], seconds: float ) -> T:

        async with asyncio.timeout(seconds): return await job

    async def retry[T] (
        self, job: Job[T], times: int = 3, delay: float = 0.1, backoff: float = 2.0,
        on: tuple[type[BaseException], ...] = (Exception,),
    ) -> T:

        wait = delay

        for attempt in range(1, times + 1):

            try: return await job()
            except on:

                if attempt == times: raise

                await asyncio.sleep(wait)

                wait *= backoff

        raise RuntimeError(times)

    async def offload[**P, T] ( self, work: Callable[P, T], *args: P.args, **kwargs: P.kwargs ) -> T:
        return await asyncio.to_thread(work, *args, **kwargs)

    def once[T] ( self, job: Job[T] ) -> Job[T]:

        lock = asyncio.Lock()
        held: list[T] = []

        @functools.wraps(job)
        async def cached () -> T:

            if held: return held[0]

            async with lock:

                if not held: held.append(await job())

            return held[0]

        return cached

    async def sleep ( self, seconds: float ) -> None:
        await asyncio.sleep(seconds)

    async def forever ( self ) -> None:
        await asyncio.Event().wait()

    def run[T] ( self, job: Task[T] ) -> T:
        return asyncio.run(job)
