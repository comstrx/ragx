from dataclasses import dataclass
from datetime import timedelta
from typing import Self

from core.parse import parse
from .format import Formatter

MINUTE = 60.0
HOUR   = 3600.0
DAY    = 86400.0
WEEK   = 604800.0
UNITS  = {
    "weeks": WEEK, "days": DAY, "hours": HOUR, "minutes": MINUTE, "seconds": 1.0, "milliseconds": 0.001,
    "microseconds": 0.000001,
}
formatter = Formatter()

@dataclass(frozen=True, slots=True, order=True)
class Duration:

    total: float = 0.0

    @classmethod
    def of ( cls, **units: float ) -> Self:

        unknown = set(units) - set(UNITS)

        if unknown: raise ValueError(sorted(unknown))

        return cls(sum(float(amount) * UNITS[unit] for unit, amount in units.items()))

    @classmethod
    def parse ( cls, value: object ) -> Self:

        if isinstance(value, Duration): return cls(value.total)
        if isinstance(value, timedelta): return cls(value.total_seconds())

        seconds = parse.duration(value, -1.0)

        if seconds < 0: raise ValueError(value)

        return cls(seconds)

    @classmethod
    def between ( cls, start: timedelta | float, end: timedelta | float ) -> Self:

        first = start.total_seconds() if isinstance(start, timedelta) else float(start)
        last  = end.total_seconds() if isinstance(end, timedelta) else float(end)

        return cls(last - first)

    def seconds ( self ) -> float:
        return self.total

    def milliseconds ( self ) -> float:
        return self.total * 1000

    def minutes ( self ) -> float:
        return self.total / MINUTE

    def hours ( self ) -> float:
        return self.total / HOUR

    def days ( self ) -> float:
        return self.total / DAY

    def weeks ( self ) -> float:
        return self.total / WEEK

    def in_ ( self, unit: str ) -> float:

        size = UNITS.get(unit if unit.endswith("s") else unit + "s")

        if size is None: raise ValueError(unit)

        return self.total / size

    def parts ( self ) -> dict[str, int]:

        left = int(abs(self.total))
        days, left = divmod(left, int(DAY))
        hours, left = divmod(left, int(HOUR))
        minutes, seconds = divmod(left, int(MINUTE))

        return {
            "days": days, "hours": hours, "minutes": minutes, "seconds": seconds,
            "milliseconds": round((abs(self.total) % 1) * 1000),
        }

    def human ( self, short: bool = False ) -> str:
        return formatter.span(self.total, short)

    def iso ( self ) -> str:

        parts = self.parts()
        time  = "".join(f"{parts[unit]}{letter}" for unit, letter in (("hours", "H"), ("minutes", "M")) if parts[unit])
        secs  = parts["seconds"] + parts["milliseconds"] / 1000

        if secs or not (parts["days"] or time): time += f"{secs:g}S"

        sign  = "-" if self.total < 0 else ""
        days  = f"{parts['days']}D" if parts["days"] else ""

        return f"{sign}P{days}{f'T{time}' if time else ''}"

    def clock ( self ) -> str:

        parts = self.parts()
        hours = parts["days"] * 24 + parts["hours"]

        return f"{hours:02d}:{parts['minutes']:02d}:{parts['seconds']:02d}"

    def timedelta ( self ) -> timedelta:
        return timedelta(seconds=self.total)

    def is_zero ( self ) -> bool:
        return self.total == 0

    def is_negative ( self ) -> bool:
        return self.total < 0

    def abs ( self ) -> Self:
        return type(self)(abs(self.total))

    def scaled ( self, factor: float ) -> Self:
        return type(self)(self.total * factor)

    def plus ( self, other: Duration | float ) -> Self:
        return type(self)(self.total + (other.total if isinstance(other, Duration) else float(other)))

    def minus ( self, other: Duration | float ) -> Self:
        return type(self)(self.total - (other.total if isinstance(other, Duration) else float(other)))

    def clamp ( self, low: Duration, high: Duration ) -> Self:
        return type(self)(max(low.total, min(self.total, high.total)))

    def dump ( self ) -> float:
        return self.total

    def __bool__ ( self ) -> bool:
        return self.total != 0

    def __str__ ( self ) -> str:
        return self.human(short=True)

    def __add__ ( self, other: Duration ) -> Duration:
        return Duration(self.total + other.total)

    def __sub__ ( self, other: Duration ) -> Duration:
        return Duration(self.total - other.total)

    def __mul__ ( self, factor: float ) -> Duration:
        return Duration(self.total * factor)

    def __truediv__ ( self, divisor: float ) -> Duration:
        return Duration(self.total / divisor)

    def __neg__ ( self ) -> Duration:
        return Duration(-self.total)
