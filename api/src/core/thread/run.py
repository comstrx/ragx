from collections.abc import Awaitable, Callable, Coroutine, Iterable
from concurrent.futures import ProcessPoolExecutor
from typing import Any
import asyncio, functools

type Job[T] = Callable[[], Awaitable[T]]
type Task[T] = Coroutine[Any, Any, T]
type Catch = tuple[type[BaseException], ...]

class Run:

    _processes : ProcessPoolExecutor | None = None

    async def gather[T] ( self, *jobs: Awaitable[T], limit: int = 0 ) -> list[T]:

        gate = asyncio.Semaphore(limit) if limit > 0 else None

        async def one ( job: Awaitable[T] ) -> T:

            if gate is None: return await job

            async with gate: return await job

        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(one(job)) for job in jobs]

        return [task.result() for task in tasks]

    async def settle[T] ( self, *jobs: Awaitable[T] ) -> list[T | BaseException]:
        return list(await asyncio.gather(*jobs, return_exceptions=True))

    async def map[T, R] ( self, fn: Callable[[T], Awaitable[R]], items: Iterable[T], limit: int = 8 ) -> list[R]:
        return await self.gather(*(fn(item) for item in items), limit=limit)

    async def first[T] ( self, *jobs: Awaitable[T] ) -> T:

        tasks = [asyncio.ensure_future(job) for job in jobs]

        try:

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in pending: task.cancel()

            return next(iter(done)).result()

        finally:
            for task in tasks: task.cancel()

    async def timeout[T] ( self, job: Awaitable[T], seconds: float ) -> T:

        async with asyncio.timeout(seconds): return await job

    async def wait_for[T] ( self, job: Awaitable[T], seconds: float, default: T ) -> T:

        try:
            async with asyncio.timeout(seconds): return await job
        except TimeoutError: return default

    async def retry[T] (
        self, job: Job[T], times: int = 3, delay: float = 0.1, backoff: float = 2.0, on: Catch = (Exception,),
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

    async def compute[T] ( self, work: Callable[..., T], *args: object ) -> T:
        return await asyncio.get_running_loop().run_in_executor(self.processes(), work, *args)

    def processes ( self, workers: int | None = None ) -> ProcessPoolExecutor:

        if self._processes is None: self._processes = ProcessPoolExecutor(max_workers=workers)

        return self._processes

    def shutdown_processes ( self ) -> None:

        pool, self._processes = self._processes, None

        if pool is not None: pool.shutdown(wait=False, cancel_futures=True)

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

    async def poll (
        self, test: Callable[[], Awaitable[bool] | bool], every: float = 0.1, within: float = 5.0,
    ) -> bool:

        loop     = asyncio.get_running_loop()
        deadline = loop.time() + within

        while True:

            found = test()
            ready = await found if isinstance(found, Awaitable) else found

            if ready: return True
            if loop.time() >= deadline: return False

            await asyncio.sleep(every)

    def run[T] ( self, job: Task[T] ) -> T:
        return asyncio.run(job)

    def loop ( self ) -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    def running ( self ) -> bool:

        try: asyncio.get_running_loop()
        except RuntimeError: return False

        return True
