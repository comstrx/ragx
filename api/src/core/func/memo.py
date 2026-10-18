from collections.abc import Callable
from typing import Any, cast
import functools, inspect, time

type Key = tuple[object, ...]

class Memoized[**P, T]:

    def __init__ ( self, fn: Callable[P, T], ttl: float | None, size: int ) -> None:

        self._fn    = fn
        self._ttl   = ttl
        self._size  = size
        self._async = inspect.iscoroutinefunction(fn)
        self._kept: dict[Key, tuple[float, Any]] = {}

        functools.update_wrapper(self, fn)

    def key ( self, args: tuple[object, ...], kwargs: dict[str, object] ) -> Key:
        return (*args, *sorted(kwargs.items()))

    def fresh ( self, entry: tuple[float, Any] | None ) -> bool:
        return entry is not None and (self._ttl is None or time.monotonic() - entry[0] < self._ttl)

    def keep ( self, mark: Key, value: object ) -> None:

        if len(self._kept) >= self._size: self._kept.pop(next(iter(self._kept)))

        self._kept[mark] = (time.monotonic(), value)

    def forget ( self, *args: object, **kwargs: object ) -> bool:

        if not args and not kwargs:

            self._kept.clear()

            return True

        return self._kept.pop(self.key(args, dict(kwargs)), None) is not None

    def size ( self ) -> int:
        return len(self._kept)

    def __call__ ( self, *args: P.args, **kwargs: P.kwargs ) -> T:

        mark  = self.key(args, kwargs)
        entry = self._kept.get(mark)

        if self._async: return cast("T", self._awaited_(mark, entry, args, kwargs))
        if self.fresh(entry) and entry is not None: return cast("T", entry[1])

        value = self._fn(*args, **kwargs)

        self.keep(mark, value)

        return value

    async def _awaited_ ( self, mark: Key, entry: tuple[float, Any] | None, args: Any, kwargs: Any ) -> Any:

        if self.fresh(entry) and entry is not None: return entry[1]

        value = await cast("Any", self._fn(*args, **kwargs))

        self.keep(mark, value)

        return value

class Memo:

    def memo[**Q, R] ( self, fn: Callable[Q, R], ttl: float | None = None, size: int = 256 ) -> Memoized[Q, R]:
        return Memoized(fn, ttl, size)

    def lazy[R] ( self, make: Callable[[], R] ) -> Callable[[], R]:

        held: list[R] = []

        def value () -> R:

            if not held: held.append(make())

            return held[0]

        return value
