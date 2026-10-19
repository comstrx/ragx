from collections.abc import Awaitable, Callable
from typing import Any
import asyncio, functools, time

type Async[**P, T] = Callable[P, Awaitable[T]]

class Limit:

    def debounce[**P] ( self, fn: Async[P, Any], seconds: float ) -> Callable[P, Awaitable[None]]:

        pending: list[asyncio.Task[None]] = []

        @functools.wraps(fn)
        async def delayed ( *args: P.args, **kwargs: P.kwargs ) -> None:

            for task in pending: task.cancel()

            pending.clear()

            async def later () -> None:

                await asyncio.sleep(seconds)
                await fn(*args, **kwargs)

            pending.append(asyncio.create_task(later()))

        return delayed

    def throttle[**P, T] ( self, fn: Async[P, T], seconds: float ) -> Callable[P, Awaitable[T | None]]:

        last = [0.0]

        @functools.wraps(fn)
        async def spaced ( *args: P.args, **kwargs: P.kwargs ) -> T | None:

            now = time.monotonic()

            if now - last[0] < seconds: return None

            last[0] = now

            return await fn(*args, **kwargs)

        return spaced

    def rate_limited[**P, T] ( self, fn: Async[P, T], calls: int, per: float ) -> Async[P, T]:

        stamps: list[float] = []
        lock   = asyncio.Lock()

        @functools.wraps(fn)
        async def paced ( *args: P.args, **kwargs: P.kwargs ) -> T:

            async with lock:

                now = time.monotonic()

                while stamps and now - stamps[0] >= per: stamps.pop(0)

                if len(stamps) >= calls:

                    await asyncio.sleep(per - (now - stamps[0]))

                    stamps.pop(0)

                stamps.append(time.monotonic())

            return await fn(*args, **kwargs)

        return paced

    def bounded[**P, T] ( self, fn: Async[P, T], limit: int ) -> Async[P, T]:

        gate = asyncio.Semaphore(max(limit, 1))

        @functools.wraps(fn)
        async def gated ( *args: P.args, **kwargs: P.kwargs ) -> T:

            async with gate: return await fn(*args, **kwargs)

        return gated

    def single_flight[**P, T] ( self, fn: Async[P, T] ) -> Async[P, T]:

        flights: dict[tuple[object, ...], asyncio.Future[T]] = {}

        @functools.wraps(fn)
        async def shared ( *args: P.args, **kwargs: P.kwargs ) -> T:

            key    = (*args, *sorted(kwargs.items()))
            flight = flights.get(key)

            if flight is not None: return await flight

            loop   = asyncio.get_running_loop()
            future: asyncio.Future[T] = loop.create_future()
            flights[key] = future

            try: value = await fn(*args, **kwargs)
            except BaseException as error:

                future.set_exception(error)

                raise

            else:

                future.set_result(value)

                return value

            finally: flights.pop(key, None)

        return shared
