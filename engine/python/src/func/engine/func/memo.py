from collections.abc import Awaitable, Callable, Hashable
from types import MethodType
from typing import Any, cast, overload

from engine.fast import Lru
from engine.json import json
import asyncio, functools, inspect

MISSING = object()

def key_of ( args: tuple[object, ...], kwargs: dict[str, object] ) -> Hashable:

    shaped = (args, tuple(sorted(kwargs.items())))

    try: hash(shaped)
    except TypeError: return json.canonical([args, kwargs])

    return shaped

class Memoized[**P, T]:

    def __init__ ( self, fn: Callable[P, T], ttl: float | None, size: int ) -> None:

        self._fn      = fn
        self._async   = inspect.iscoroutinefunction(fn)
        self._kept: Lru[Hashable, Any] = Lru(size, ttl)
        self._flights: dict[Hashable, asyncio.Future[Any]] = {}
        self._shared  = 0

        functools.update_wrapper(self, fn)

    def __call__ ( self, *args: P.args, **kwargs: P.kwargs ) -> T:

        mark = key_of(args, kwargs)

        if self._async: return cast("T", self._awaited_(mark, args, kwargs))

        found = self._kept.get(mark, MISSING)

        if found is not MISSING: return cast("T", found)

        value = self._fn(*args, **kwargs)

        self._kept.set(mark, value)

        return value

    def __get__ ( self, instance: object, owner: type | None = None ) -> Any:

        return self if instance is None else MethodType(self, instance)

    async def _awaited_ ( self, mark: Hashable, args: Any, kwargs: Any ) -> Any:

        found = self._kept.get(mark, MISSING)

        if found is not MISSING: return found

        flight = self._flights.get(mark)

        if flight is not None:

            self._shared += 1

            return await asyncio.shield(flight)

        flight = asyncio.get_running_loop().create_future()
        self._flights[mark] = flight

        try: value = await cast("Awaitable[Any]", self._fn(*args, **kwargs))
        except BaseException as error:

            if not flight.done(): flight.set_exception(error)

            flight.exception()

            raise

        finally: self._flights.pop(mark, None)

        self._kept.set(mark, value)
        flight.set_result(value)

        return value

    def forget ( self, *args: object, **kwargs: object ) -> bool:

        return self._kept.pop(key_of(args, dict(kwargs)), MISSING) is not MISSING

    def clear ( self ) -> int:

        return self._kept.clear()

    def size ( self ) -> int:

        return len(self._kept)

    def stats ( self ) -> dict[str, Any]:

        return { **self._kept.stats(), "shared": self._shared, "flights": len(self._flights) }

class Memo:

    @overload
    def memo[**Q, R] ( self, fn: Callable[Q, R], *, ttl: float | None = None, size: int = 256 ) -> Memoized[Q, R]: ...

    @overload
    def memo[**Q, R] (
        self, fn: None = None, *, ttl: float | None = None, size: int = 256,
    ) -> Callable[[Callable[Q, R]], Memoized[Q, R]]: ...

    def memo[**Q, R] (
        self, fn: Callable[Q, R] | None = None, *, ttl: float | None = None, size: int = 256,
    ) -> Memoized[Q, R] | Callable[[Callable[Q, R]], Memoized[Q, R]]:

        if fn is not None: return Memoized(fn, ttl, size)

        def wrap ( target: Callable[Q, R] ) -> Memoized[Q, R]:

            return Memoized(target, ttl, size)

        return wrap

    def lru[F: Callable[..., Any]] ( self, size: int | None = 128 ) -> Callable[[F], F]:

        def wrap ( target: F ) -> F:

            return cast("F", functools.lru_cache(maxsize=size)(target))

        return wrap

    def cache[F: Callable[..., Any]] ( self, fn: F ) -> F:

        return cast("F", functools.cache(fn))

    def dispatch[F: Callable[..., Any]] ( self, fn: F ) -> Any:

        return functools.singledispatch(fn)

    def wraps[F: Callable[..., Any]] ( self, original: Callable[..., Any] ) -> Callable[[F], F]:

        def wrap ( target: F ) -> F:

            return cast("F", functools.wraps(original)(target))

        return wrap

    def lazy[R] ( self, make: Callable[[], R] ) -> Callable[[], R]:

        held: list[R] = []

        def value () -> R:

            if not held: held.append(make())

            return held[0]

        return value
