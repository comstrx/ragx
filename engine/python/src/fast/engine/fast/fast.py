from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any

from .lru import Lru
from .ttl import Ttl
import time

BUCKETS = 4096

@dataclass(frozen=True, slots=True)
class Verdict:

    allowed   : bool
    remaining : int
    reset     : float
    count     : int

class Window:

    def __init__ ( self, clock: Callable[[], float] = time.monotonic ) -> None:

        self._clock   = clock
        self._buckets: dict[str, tuple[float, int]] = {}

    def hit ( self, key: str, limit: int, window: float, cost: int = 1 ) -> Verdict:

        now    = self._clock()
        bucket = self._buckets.get(key)

        if bucket is None or bucket[0] <= now: bucket = (now + window, 0)

        count = bucket[1] + cost

        self._buckets[key] = (bucket[0], count)

        if len(self._buckets) > BUCKETS: self.sweep()

        return Verdict(count <= limit, max(limit - count, 0), max(bucket[0] - now, 0.0), count)

    def peek ( self, key: str, limit: int ) -> Verdict:

        now    = self._clock()
        bucket = self._buckets.get(key)

        if bucket is None or bucket[0] <= now: return Verdict(allowed=True, remaining=limit, reset=0.0, count=0)

        return Verdict(bucket[1] < limit, max(limit - bucket[1], 0), bucket[0] - now, bucket[1])

    def reset ( self, key: str ) -> bool:

        return self._buckets.pop(key, None) is not None

    def sweep ( self ) -> int:

        now  = self._clock()
        dead = [key for key, (expiry, _) in self._buckets.items() if expiry <= now]

        for key in dead: self._buckets.pop(key, None)

        return len(dead)

    def clear ( self ) -> int:

        count = len(self._buckets)

        self._buckets.clear()

        return count

    def stats ( self ) -> dict[str, Any]:

        return { "buckets": len(self._buckets) }

class Sliding:

    def __init__ ( self, clock: Callable[[], float] = time.monotonic ) -> None:

        self._clock = clock
        self._logs: dict[str, list[float]] = {}

    def hit ( self, key: str, limit: int, window: float ) -> Verdict:

        now   = self._clock()
        edge  = now - window
        stamps = [stamp for stamp in self._logs.get(key, []) if stamp > edge]

        stamps.append(now)

        self._logs[key] = stamps

        oldest = stamps[0] if stamps else now

        return Verdict(len(stamps) <= limit, max(limit - len(stamps), 0), max(oldest + window - now, 0.0), len(stamps))

    def reset ( self, key: str ) -> bool:

        return self._logs.pop(key, None) is not None

    def clear ( self ) -> int:

        count = len(self._logs)

        self._logs.clear()

        return count

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

    def clear ( self ) -> int:

        return self._store.clear() + self._window.clear()

    def stats ( self ) -> dict[str, Any]:

        return { **self._store.stats(), **self._window.stats() }
