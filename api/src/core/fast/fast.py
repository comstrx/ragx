from collections.abc import Callable, Hashable
from typing import Any

from .lru import Lru
from .rate import Sliding, Verdict, Window
from .ttl import Ttl

class Fast:

    def __init__ ( self ) -> None:

        self._store: Ttl[str, Any] = Ttl()
        self._window = Window()

    def lru[K: Hashable, V] ( self, size: int = 1024 ) -> Lru[K, V]:
        return Lru(size)

    def ttl[K: Hashable, V] ( self, sweep: int = 512 ) -> Ttl[K, V]:
        return Ttl(sweep)

    def window ( self ) -> Window:
        return Window()

    def sliding ( self ) -> Sliding:
        return Sliding()

    def get ( self, key: str, default: Any = None ) -> Any:
        return self._store.get(key, default)

    def set ( self, key: str, value: object, ttl: float | None = None ) -> None:
        self._store.set(key, value, ttl)

    def add ( self, key: str, value: object, ttl: float | None = None ) -> bool:
        return self._store.add(key, value, ttl)

    def remember[T] ( self, key: str, make: Callable[[], T], ttl: float | None = None ) -> T:

        found: T = self._store.remember(key, make, ttl)

        return found

    def forget ( self, key: str ) -> bool:
        return self._store.delete(key)

    def pull ( self, key: str, default: Any = None ) -> Any:
        return self._store.pull(key, default)

    def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:
        return self._store.increment(key, step, ttl)

    def has ( self, key: str ) -> bool:
        return self._store.has(key)

    def hit ( self, key: str, limit: int, window: float ) -> Verdict:
        return self._window.hit(key, limit, window)

    def clear ( self ) -> None:

        self._store.clear()
        self._window.clear()

    def stats ( self ) -> dict[str, Any]:
        return { **self._store.stats(), **self._window.stats() }
