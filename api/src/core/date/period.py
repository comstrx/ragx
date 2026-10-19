from collections.abc import Iterator
from dataclasses import dataclass
from typing import Self

from core.error import Code, Fault
from .duration import Duration
from .moment import Moment

STEPS = {
    "second": "seconds", "minute": "minutes", "hour": "hours", "day": "days", "week": "weeks", "month": "months",
    "year": "years",
}

@dataclass(frozen=True, slots=True)
class Period:

    start : Moment
    end   : Moment

    @classmethod
    def of ( cls, start: object, end: object ) -> Self:

        first = Moment.wrap(start)
        last  = Moment.wrap(end)

        return cls(first, last) if first <= last else cls(last, first)

    @classmethod
    def around ( cls, center: Moment, duration: Duration ) -> Self:

        return cls(center.shift(duration.scaled(-0.5)), center.shift(duration.scaled(0.5)))

    @classmethod
    def unit ( cls, moment: Moment, unit: str ) -> Self:

        return cls(moment.start_of(unit), moment.end_of(unit))

    def length ( self ) -> Duration:

        return self.start.diff(self.end)

    def each ( self, unit: str = "day", step: int = 1 ) -> Iterator[Moment]:

        if unit not in STEPS or step < 1: raise Fault(Code.BAD_REQUEST, reason="date.unit")

        current = self.start
        shift   = { STEPS[unit]: step }

        while current <= self.end:

            yield current

            current = current.add(**shift)

    def count ( self, unit: str = "day", step: int = 1 ) -> int:

        return sum(1 for _ in self.each(unit, step))

    def days ( self ) -> list[Moment]:

        return list(self.each("day"))

    def contains ( self, moment: Moment, inclusive: bool = True ) -> bool:

        return moment.is_between(self.start, self.end, inclusive)

    def overlaps ( self, other: Period ) -> bool:

        return self.start <= other.end and other.start <= self.end

    def intersect ( self, other: Period ) -> Period | None:

        if not self.overlaps(other): return None

        return Period(max(self.start, other.start), min(self.end, other.end))

    def merge ( self, other: Period ) -> Period:

        return Period(min(self.start, other.start), max(self.end, other.end))

    def split ( self, count: int ) -> list[Period]:

        if count < 1: raise Fault(Code.BAD_REQUEST, reason="date.split")

        piece  = self.length().scaled(1 / count)
        pieces: list[Period] = []
        cursor = self.start

        for index in range(count):

            last = self.end if index == count - 1 else cursor.shift(piece)

            pieces.append(Period(cursor, last))

            cursor = last

        return pieces

    def shift ( self, duration: Duration ) -> Period:

        return Period(self.start.shift(duration), self.end.shift(duration))

    def is_empty ( self ) -> bool:

        return self.start.at == self.end.at

    def dump ( self ) -> dict[str, str]:

        return { "start": self.start.iso(), "end": self.end.iso() }

    def __iter__ ( self ) -> Iterator[Moment]:

        return self.each("day")

    def __contains__ ( self, moment: object ) -> bool:

        return isinstance(moment, Moment) and self.contains(moment)
