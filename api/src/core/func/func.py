from collections.abc import Awaitable, Callable
from typing import Any, cast

from .call import Call
from .limit import Limit
from .memo import Memo
from .retry import Retry
import asyncio, functools, inspect, time

type Fn[**P, T] = Callable[P, T]
type Catch = tuple[type[BaseException], ...]
type Report = Callable[[str, float], None]

class Guard:

    def safe[**P, T] ( self, fn: Fn[P, T], default: T, on: Catch = (Exception,) ) -> Fn[P, T]:

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def guarded_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                try: return await cast("Awaitable[object]", fn(*args, **kwargs))
                except on: return default

            return cast("Fn[P, T]", guarded_async)

        @functools.wraps(fn)
        def guarded ( *args: P.args, **kwargs: P.kwargs ) -> T:

            try: return fn(*args, **kwargs)
            except on: return default

        return guarded

    def attempt[T] ( self, fn: Callable[[], T], default: T | None = None, on: Catch = (Exception,) ) -> T | None:

        try: return fn()
        except on: return default

    async def attempt_async[T] (
        self, fn: Callable[[], Awaitable[T]], default: T | None = None, on: Catch = (Exception,),
    ) -> T | None:

        try: return await fn()
        except on: return default

    def once[**P, T] ( self, fn: Fn[P, T] ) -> Fn[P, T]:

        held: list[Any] = []

        if inspect.iscoroutinefunction(fn):

            lock = asyncio.Lock()

            @functools.wraps(fn)
            async def first_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                async with lock:

                    if not held: held.append(await cast("Awaitable[object]", fn(*args, **kwargs)))

                return held[0]

            return cast("Fn[P, T]", first_async)

        @functools.wraps(fn)
        def first ( *args: P.args, **kwargs: P.kwargs ) -> T:

            if not held: held.append(fn(*args, **kwargs))

            return cast("T", held[0])

        return first

    def fallback[**P, T] ( self, fn: Fn[P, T], *alternatives: Fn[P, T], on: Catch = (Exception,) ) -> Fn[P, T]:

        chain = (fn, *alternatives)

        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def chained_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                for candidate in chain[:-1]:

                    try: return await cast("Awaitable[object]", candidate(*args, **kwargs))
                    except on: continue

                return await cast("Awaitable[object]", chain[-1](*args, **kwargs))

            return cast("Fn[P, T]", chained_async)

        @functools.wraps(fn)
        def chained ( *args: P.args, **kwargs: P.kwargs ) -> T:

            for candidate in chain[:-1]:

                try: return candidate(*args, **kwargs)
                except on: continue

            return chain[-1](*args, **kwargs)

        return chained

    def when[**P, T] ( self, condition: Callable[[], bool], fn: Fn[P, T], otherwise: Fn[P, T] ) -> Fn[P, T]:

        @functools.wraps(fn)
        def chosen ( *args: P.args, **kwargs: P.kwargs ) -> T:

            return fn(*args, **kwargs) if condition() else otherwise(*args, **kwargs)

        return chosen

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

class Func(Call, Guard, Memo, Retry, Limit, Measure):

    __slots__ = ()
