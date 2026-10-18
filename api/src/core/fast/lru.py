from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterator
from typing import Any, cast

MISSING = object()

class Lru[K: Hashable, V]:

    def __init__ ( self, size: int = 1024 ) -> None:

        self._size = max(size, 1)
        self._data: OrderedDict[K, V] = OrderedDict()
        self._hits   = 0
        self._misses = 0

    def get ( self, key: K, default: V | None = None ) -> V | None:

        found = self._data.get(key, MISSING)

        if found is MISSING:

            self._misses += 1

            return default

        self._data.move_to_end(key)
        self._hits += 1

        return cast("V", found)

    def set ( self, key: K, value: V ) -> None:

        self._data[key] = value
        self._data.move_to_end(key)

        while len(self._data) > self._size: self._data.popitem(last=False)

    def remember ( self, key: K, make: Callable[[], V] ) -> V:

        found = self._data.get(key, MISSING)

        if found is not MISSING:

            self._data.move_to_end(key)
            self._hits += 1

            return cast("V", found)

        self._misses += 1
        value = make()

        self.set(key, value)

        return value

    def pop ( self, key: K, default: V | None = None ) -> V | None:
        return self._data.pop(key, default)

    def has ( self, key: K ) -> bool:
        return key in self._data

    def clear ( self ) -> None:
        self._data.clear()

    def keys ( self ) -> list[K]:
        return list(self._data)

    def oldest ( self ) -> K | None:
        return next(iter(self._data), None)

    def newest ( self ) -> K | None:
        return next(reversed(self._data), None)

    def resize ( self, size: int ) -> None:

        self._size = max(size, 1)

        while len(self._data) > self._size: self._data.popitem(last=False)

    def stats ( self ) -> dict[str, Any]:
        return { "size": len(self._data), "limit": self._size, "hits": self._hits, "misses": self._misses }

    def __len__ ( self ) -> int:
        return len(self._data)

    def __contains__ ( self, key: object ) -> bool:
        return key in self._data

    def __iter__ ( self ) -> Iterator[K]:
        return iter(list(self._data))
