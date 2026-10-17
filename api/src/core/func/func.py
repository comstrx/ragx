from collections.abc import Awaitable, Callable
from typing import Any, cast
import asyncio, functools, inspect, time

type Fn[**P, T] = Callable[P, T]

class Func:

    def name ( self, fn: Callable[..., object] ) -> str:
        return f"{fn.__module__}.{getattr(fn, '__qualname__', type(fn).__name__)}"

    def is_async ( self, fn: Callable[..., object] ) -> bool:
        return inspect.iscoroutinefunction(fn)

    def arguments ( self, fn: Callable[..., object] ) -> dict[str, object]:

        empty = inspect.Parameter.empty

        return {
            name: (None if parameter.default is empty else parameter.default)
            for name, parameter in inspect.signature(fn).parameters.items()
        }

    async def call ( self, fn: Callable[..., object], *args: object, **kwargs: object ) -> Any:

        result = fn(*args, **kwargs)

        return await result if inspect.isawaitable(result) else result

    def pipe[T] ( self, *steps: Callable[[T], T] ) -> Callable[[T], T]:

        def run ( value: T ) -> T:

            for step in steps: value = step(value)

            return value

        return run

    def safe[**P, T] ( self, fn: Fn[P, T], default: T, on: tuple[type[BaseException], ...] = (Exception,) ) -> Fn[P, T]:

        if self.is_async(fn):

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

    def once[**P, T] ( self, fn: Fn[P, T] ) -> Fn[P, T]:

        held: list[Any] = []

        if self.is_async(fn):

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

    def memo[**P, T] ( self, fn: Fn[P, T], ttl: float | None = None, size: int = 256 ) -> Fn[P, T]:

        kept: dict[tuple[object, ...], tuple[float, Any]] = {}

        def key ( args: tuple[object, ...], kwargs: dict[str, object] ) -> tuple[object, ...]:
            return (*args, *sorted(kwargs.items()))

        def fresh ( entry: tuple[float, Any] | None ) -> bool:
            return entry is not None and (ttl is None or time.monotonic() - entry[0] < ttl)

        def keep ( mark: tuple[object, ...], value: object ) -> None:

            if len(kept) >= size: kept.pop(next(iter(kept)))

            kept[mark] = (time.monotonic(), value)

        if self.is_async(fn):

            @functools.wraps(fn)
            async def remembered_async ( *args: P.args, **kwargs: P.kwargs ) -> object:

                mark  = key(args, kwargs)
                entry = kept.get(mark)

                if fresh(entry) and entry is not None: return entry[1]

                value = await cast("Awaitable[object]", fn(*args, **kwargs))

                keep(mark, value)

                return value

            return cast("Fn[P, T]", remembered_async)

        @functools.wraps(fn)
        def remembered ( *args: P.args, **kwargs: P.kwargs ) -> T:

            mark  = key(args, kwargs)
            entry = kept.get(mark)

            if fresh(entry) and entry is not None: return cast("T", entry[1])

            value = fn(*args, **kwargs)

            keep(mark, value)

            return value

        return remembered

    def retry[**P, T] (
        self, fn: Fn[P, T], times: int = 3, delay: float = 0.1, backoff: float = 2.0,
        on: tuple[type[BaseException], ...] = (Exception,),
    ) -> Fn[P, T]:

        if times < 1: raise ValueError(times)

        waits = [delay * (backoff ** step) for step in range(times - 1)]

        if self.is_async(fn):

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

        if not self.is_async(fn): raise TypeError(self.name(fn))

        @functools.wraps(fn)
        async def bounded ( *args: P.args, **kwargs: P.kwargs ) -> T:

            async with asyncio.timeout(seconds): return await fn(*args, **kwargs)

        return bounded

    def measure[**P, T] ( self, fn: Fn[P, T], report: Callable[[str, float], None] ) -> Fn[P, T]:

        label = self.name(fn)

        if self.is_async(fn):

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
