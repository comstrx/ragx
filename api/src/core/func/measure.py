from collections.abc import Awaitable, Callable
from typing import cast
import functools, inspect, time

type Fn[**P, T] = Callable[P, T]
type Report = Callable[[str, float], None]

class Measure:

    def measure[**P, T] ( self, fn: Fn[P, T], report: Report ) -> Fn[P, T]:

        label = f"{fn.__module__}.{getattr(fn, '__qualname__', type(fn).__name__)}"

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def timed_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                started = time.perf_counter()

                try: return await cast("Awaitable[object]", fn(*args, **kwargs))
                finally: report(label, round((time.perf_counter() - started) * 1000, 3))

            return cast("Fn[P, T]", timed_async)

        @functools.wraps(fn)
        def timed ( *args: P.args, **kwargs: P.kwargs ) -> T:

            started = time.perf_counter()

            try: return fn(*args, **kwargs)
            finally: report(label, round((time.perf_counter() - started) * 1000, 3))

        return timed

    def timed[T] ( self, fn: Callable[[], T] ) -> tuple[T, float]:

        started = time.perf_counter()
        result  = fn()

        return result, round((time.perf_counter() - started) * 1000, 3)

    async def timed_async[T] ( self, fn: Callable[[], Awaitable[T]] ) -> tuple[T, float]:

        started = time.perf_counter()
        result  = await fn()

        return result, round((time.perf_counter() - started) * 1000, 3)

    def counted[**P, T] ( self, fn: Fn[P, T] ) -> tuple[Fn[P, T], Callable[[], int]]:

        calls = [0]

        @functools.wraps(fn)
        def counting ( *args: P.args, **kwargs: P.kwargs ) -> T:

            calls[0] += 1

            return fn(*args, **kwargs)

        return counting, lambda: calls[0]
