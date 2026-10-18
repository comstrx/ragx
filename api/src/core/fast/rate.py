from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
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

    def clear ( self ) -> None:
        self._buckets.clear()

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

    def clear ( self ) -> None:
        self._logs.clear()
