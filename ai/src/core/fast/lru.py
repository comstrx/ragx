from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from typing import Any, cast
import time

type Entry[V] = tuple[float | None, V]

class Lru[K: Hashable, V]:

    def __init__ (
        self, size: int = 1024, ttl: float | None = None, clock: Callable[[], float] = time.monotonic,
    ) -> None:

        self._size  = max(size, 1)
        self._ttl   = ttl
        self._clock = clock
        self._data: OrderedDict[K, Entry[V]] = OrderedDict()
        self._hits      = 0
        self._misses    = 0
        self._evictions = 0

    def entry ( self, key: K ) -> Entry[V] | None:

        found = self._data.get(key)

        if found is None: return None
        if found[0] is not None and found[0] <= self._clock():

            del self._data[key]

            return None

        return found

    def get ( self, key: K, default: V | None = None ) -> V | None:

        found = self.entry(key)

        if found is None:

            self._misses += 1

            return default

        self._data.move_to_end(key)
        self._hits += 1

        return found[1]

    def set ( self, key: K, value: V, ttl: float | None = None ) -> None:

        span = ttl if ttl is not None else self._ttl

        self._data[key] = (self._clock() + span if span else None, value)
        self._data.move_to_end(key)

        while len(self._data) > self._size:

            self._data.popitem(last=False)
            self._evictions += 1

    def add ( self, key: K, value: V, ttl: float | None = None ) -> bool:

        if self.entry(key) is not None: return False

        self.set(key, value, ttl)

        return True

    def remember ( self, key: K, make: Callable[[], V], ttl: float | None = None ) -> V:

        found = self.entry(key)

        if found is not None:

            self._data.move_to_end(key)
            self._hits += 1

            return found[1]

        self._misses += 1
        value = make()

        self.set(key, value, ttl)

        return value

    def pop ( self, key: K, default: V | None = None ) -> V | None:

        found = self.entry(key)

        if found is None: return default

        del self._data[key]

        return found[1]

    def has ( self, key: K ) -> bool:

        return self.entry(key) is not None

    def ttl ( self, key: K ) -> float | None:

        found = self.entry(key)

        return None if found is None or found[0] is None else max(found[0] - self._clock(), 0.0)

    def clear ( self ) -> int:

        count = len(self._data)

        self._data.clear()

        return count

    def keys ( self ) -> list[K]:

        return [key for key in list(self._data) if self.entry(key) is not None]

    def oldest ( self ) -> K | None:

        return next(iter(self._data), None)

    def newest ( self ) -> K | None:

        return next(reversed(self._data), None)

    def resize ( self, size: int ) -> None:

        self._size = max(size, 1)

        while len(self._data) > self._size:

            self._data.popitem(last=False)
            self._evictions += 1

    def stats ( self ) -> dict[str, Any]:

        return {
            "size": len(self._data), "limit": self._size, "hits": self._hits, "misses": self._misses,
            "evictions": self._evictions,
        }

    def __len__ ( self ) -> int:

        return len(self._data)

    def __contains__ ( self, key: object ) -> bool:

        return key in self._data and self.entry(cast("K", key)) is not None

    def __iter__ ( self ) -> Iterator[K]:

        return iter(self.keys())
