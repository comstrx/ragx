from collections.abc import Sequence
from dataclasses import dataclass
from core.error import Code, Fault
import math

class Vector:

    def validate ( self, values: Sequence[float], dimension: int | None = None ) -> tuple[float, ...]:

        if any(type(value) not in (int, float) for value in values):
            raise Fault(Code.VALIDATION, reason="vector.type")
        result = tuple(float(value) for value in values)

        if not result or any(not math.isfinite(value) for value in result):
            raise Fault(Code.VALIDATION, reason="vector.values")
        if dimension is not None and len(result) != dimension:
            raise Fault(Code.VALIDATION, reason="vector.dimension")

        return result

    def normalize ( self, values: Sequence[float] ) -> tuple[float, ...]:

        vector = self.validate(values)
        norm = math.hypot(*vector)

        if norm == 0: raise Fault(Code.VALIDATION, reason="vector.zero")

        return tuple(value / norm for value in vector)

    def cosine ( self, left: Sequence[float], right: Sequence[float] ) -> float:

        self.validate(right, len(left))

        return math.fsum(a * b for a, b in zip(self.normalize(left), self.normalize(right), strict=True))

    def sigmoid ( self, value: float ) -> float:

        if not math.isfinite(value): raise Fault(Code.VALIDATION, reason="number.finite")
        if value >= 0: return 1 / (1 + math.exp(-value))

        exponential = math.exp(value)

        return exponential / (1 + exponential)

@dataclass(frozen=True, slots=True)
class UnitVector:

    values : tuple[float, ...]

    def __post_init__ ( self ) -> None:

        object.__setattr__(self, "values", Vector().normalize(self.values))

    def cosine ( self, other: UnitVector ) -> float:

        if len(self.values) != len(other.values): raise Fault(Code.VALIDATION, reason="vector.dimension")
        return max(-1.0, min(1.0, math.sumprod(self.values, other.values)))
