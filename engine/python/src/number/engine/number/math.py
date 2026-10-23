from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

from engine.error import Code, Fault
import math, statistics

type Embedding = tuple[float, ...]

class Math:

    def clamp ( self, value: float, low: float, high: float ) -> float:

        return max(low, min(value, high))

    def between ( self, value: float, low: float, high: float ) -> bool:

        return low <= value <= high

    def ratio ( self, part: float, total: float, default: float = 0.0 ) -> float:

        return part / total if total else default

    def percent ( self, part: float, total: float, digits: int = 2 ) -> float:

        return self.round(self.ratio(part, total) * 100, digits)

    def of_percent ( self, percent: float, total: float, digits: int = 2 ) -> float:

        return self.round(total * percent / 100, digits)

    def round ( self, value: float, digits: int = 2 ) -> float:

        places = Decimal(1).scaleb(-digits)

        return float(Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP))

    def floor ( self, value: float, digits: int = 0 ) -> float:

        factor = 10 ** digits

        return math.floor(value * factor) / factor if digits else float(math.floor(value))

    def ceil ( self, value: float, digits: int = 0 ) -> float:

        factor = 10 ** digits

        return math.ceil(value * factor) / factor if digits else float(math.ceil(value))

    def sign ( self, value: float ) -> int:

        return (value > 0) - (value < 0)

    def divide ( self, left: float, right: float, default: float = 0.0 ) -> float:

        return left / right if right else default

    def total ( self, values: Iterable[float] ) -> float:

        return math.fsum(values)

    def average ( self, values: Iterable[float], default: float = 0.0 ) -> float:

        items = list(values)

        return statistics.fmean(items) if items else default

    def median ( self, values: Iterable[float], default: float = 0.0 ) -> float:

        items = list(values)

        return float(statistics.median(items)) if items else default

    def percentile ( self, values: Iterable[float], rank: float, default: float = 0.0 ) -> float:

        items = sorted(values)

        if not items: return default
        if len(items) == 1: return float(items[0])

        position = (len(items) - 1) * self.clamp(rank, 0, 100) / 100
        low      = math.floor(position)
        high     = min(low + 1, len(items) - 1)

        return float(items[low] + (items[high] - items[low]) * (position - low))

    def deviation ( self, values: Iterable[float], default: float = 0.0 ) -> float:

        items = list(values)

        return statistics.pstdev(items) if items else default

    def minimum ( self, values: Iterable[float], default: float = 0.0 ) -> float:

        items = list(values)

        return min(items) if items else default

    def maximum ( self, values: Iterable[float], default: float = 0.0 ) -> float:

        items = list(values)

        return max(items) if items else default

    def spread ( self, values: Iterable[float] ) -> float:

        items = list(values)

        return (max(items) - min(items)) if items else 0.0

    def nearest ( self, value: float, step: float ) -> float:

        return round(value / step) * step if step else value

    def is_even ( self, value: int ) -> bool:

        return value % 2 == 0

    def is_odd ( self, value: int ) -> bool:

        return value % 2 == 1

    def gcd ( self, *values: int ) -> int:

        return math.gcd(*values)

    def lcm ( self, *values: int ) -> int:

        return math.lcm(*values)

    def pages ( self, total: int, limit: int ) -> int:

        return max(-(-max(total, 0) // max(limit, 1)), 1)

class Vector:

    def of ( self, values: Iterable[float], dimension: int | None = None ) -> Embedding:

        items = tuple(values)

        if any(type(value) not in (int, float) for value in items): raise Fault(Code.VALIDATION, reason="vector.type")

        found = tuple(float(value) for value in items)

        if not found or not all(map(math.isfinite, found)): raise Fault(Code.VALIDATION, reason="vector.values")
        if dimension is not None and len(found) != dimension: raise Fault(Code.VALIDATION, reason="vector.dimension")

        return found

    def norm ( self, values: Sequence[float] ) -> float:

        return math.hypot(*self.of(values))

    def unit ( self, values: Sequence[float] ) -> Embedding:

        found  = self.of(values)
        length = math.hypot(*found)

        if length == 0: raise Fault(Code.VALIDATION, reason="vector.zero")

        return tuple(value / length for value in found)

    def dot ( self, left: Sequence[float], right: Sequence[float] ) -> float:

        if len(left) != len(right): raise Fault(Code.VALIDATION, reason="vector.dimension")

        return math.sumprod(left, right)

    def cosine ( self, left: Sequence[float], right: Sequence[float] ) -> float:

        return max(-1.0, min(1.0, self.dot(self.unit(left), self.unit(right))))
