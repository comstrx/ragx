from collections.abc import Callable, Hashable, Iterator
from typing import Any, cast
import time

type Entry[V] = tuple[float | None, V]

class Ttl[K: Hashable, V]:

    def __init__ ( self, sweep: int = 512, clock: Callable[[], float] = time.monotonic ) -> None:

        self._sweep   = max(sweep, 1)
        self._clock   = clock
        self._entries: dict[K, Entry[V]] = {}

    def entry ( self, key: K ) -> Entry[V] | None:

        found = self._entries.get(key)

        if found is None: return None
        if found[0] is not None and found[0] <= self._clock():

            self._entries.pop(key, None)

            return None

        return found

    def get ( self, key: K, default: V | None = None ) -> V | None:

        found = self.entry(key)

        return default if found is None else found[1]

    def set ( self, key: K, value: V, ttl: float | None = None ) -> None:

        if len(self._entries) >= self._sweep: self.sweep()

        self._entries[key] = (self._clock() + ttl if ttl else None, value)

    def add ( self, key: K, value: V, ttl: float | None = None ) -> bool:

        if self.entry(key) is not None: return False

        self.set(key, value, ttl)

        return True

    def remember ( self, key: K, make: Callable[[], V], ttl: float | None = None ) -> V:

        found = self.entry(key)

        if found is not None: return found[1]

        value = make()

        self.set(key, value, ttl)

        return value

    def delete ( self, key: K ) -> bool:
        return self._entries.pop(key, None) is not None

    def pull ( self, key: K, default: V | None = None ) -> V | None:

        found = self.get(key, default)

        self._entries.pop(key, None)

        return found

    def increment ( self, key: K, step: int = 1, ttl: float | None = None ) -> int:

        found   = self.entry(key)
        current = int(cast("int", found[1])) if found is not None and isinstance(found[1], int) else 0
        expiry  = found[0] if found is not None else (self._clock() + ttl if ttl else None)

        self._entries[key] = (expiry, cast("V", current + step))

        return current + step

    def ttl ( self, key: K ) -> float | None:

        found = self.entry(key)

        if found is None or found[0] is None: return None

        return max(found[0] - self._clock(), 0.0)

    def touch ( self, key: K, ttl: float ) -> bool:

        found = self.entry(key)

        if found is None: return False

        self._entries[key] = (self._clock() + ttl, found[1])

        return True

    def has ( self, key: K ) -> bool:
        return self.entry(key) is not None

    def clear ( self ) -> None:
        self._entries.clear()

    def sweep ( self ) -> int:

        now  = self._clock()
        dead = [key for key, (expiry, _) in self._entries.items() if expiry is not None and expiry <= now]

        for key in dead: self._entries.pop(key, None)

        return len(dead)

    def keys ( self ) -> list[K]:

        self.sweep()

        return list(self._entries)

    def stats ( self ) -> dict[str, Any]:
        return { "size": len(self._entries), "sweep": self._sweep }

    def __len__ ( self ) -> int:
        return len(self._entries)

    def __contains__ ( self, key: object ) -> bool:
        return self.entry(cast("K", key)) is not None

    def __iter__ ( self ) -> Iterator[K]:
        return iter(self.keys())
