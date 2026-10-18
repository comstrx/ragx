from collections.abc import Awaitable, Callable
from typing import cast
import asyncio, functools, inspect, time

type Fn[**P, T] = Callable[P, T]
type Catch = tuple[type[BaseException], ...]

class Retry:

    def waits ( self, times: int, delay: float, backoff: float, cap: float | None = None ) -> list[float]:

        if times < 1: raise ValueError(times)

        found = [delay * (backoff ** step) for step in range(times - 1)]

        return [min(wait, cap) if cap is not None else wait for wait in found]

    def retry[**P, T] (
        self, fn: Fn[P, T], times: int = 3, delay: float = 0.1, backoff: float = 2.0,
        on: Catch = (Exception,), cap: float | None = None,
    ) -> Fn[P, T]:

        waits = self.waits(times, delay, backoff, cap)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def again_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                for wait in waits:

                    try: return await cast("Awaitable[object]", fn(*args, **kwargs))
                    except on: await asyncio.sleep(wait)

                return await cast("Awaitable[object]", fn(*args, **kwargs))

            return cast("Fn[P, T]", again_async)

        @functools.wraps(fn)
        def again ( *args: P.args, **kwargs: P.kwargs ) -> T:

            for wait in waits:

                try: return fn(*args, **kwargs)
                except on: time.sleep(wait)

            return fn(*args, **kwargs)

        return again

    def timeout[**P, T] ( self, fn: Fn[P, Awaitable[T]], seconds: float ) -> Fn[P, Awaitable[T]]:

        if not inspect.iscoroutinefunction(fn): raise TypeError(getattr(fn, "__qualname__", "fn"))

        @functools.wraps(fn)
        async def bounded ( *args: P.args, **kwargs: P.kwargs ) -> T:

            async with asyncio.timeout(seconds): return await fn(*args, **kwargs)

        return bounded

    def until[T] (
        self, fn: Callable[[], T], done: Callable[[T], bool], times: int = 10, delay: float = 0.1, backoff: float = 1.0,
    ) -> T:

        result = fn()

        for wait in self.waits(times, delay, backoff):

            if done(result): return result

            time.sleep(wait)

            result = fn()

        return result

    async def until_async[T] (
        self, fn: Callable[[], Awaitable[T]], done: Callable[[T], bool],
        times: int = 10, delay: float = 0.1, backoff: float = 1.0,
    ) -> T:

        result = await fn()

        for wait in self.waits(times, delay, backoff):

            if done(result): return result

            await asyncio.sleep(wait)

            result = await fn()

        return result
