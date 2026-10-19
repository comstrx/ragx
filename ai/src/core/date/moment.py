from dataclasses import dataclass
from datetime import UTC, date as calendar, datetime, timedelta, tzinfo
from typing import Any, Self, override

from core.error import Code, Fault
from .clock import aware, clock, zone_of
from .compare import Compare
from .duration import Duration
from .format import Formatter
from .human import Human
from .parser import Parser
import calendar as months, time

MONTHS    = 12
SHIFTS    = ("years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds")
WORDS     = { "now": 0, "today": 0, "tomorrow": 1, "yesterday": -1 }
formatter = Formatter()
human     = Human()
natural   = Parser()

@dataclass(frozen=True, slots=True, order=True)
class Moment(Compare):

    at: datetime

    @classmethod
    def now ( cls, zone: str | tzinfo | None = None ) -> Self:

        return cls(clock.now(zone))

    @classmethod
    def today ( cls, zone: str | tzinfo | None = None ) -> Self:

        return cls.now(zone).start_of("day")

    @classmethod
    def tomorrow ( cls, zone: str | tzinfo | None = None ) -> Self:

        return cls.today(zone).add(days=1)

    @classmethod
    def yesterday ( cls, zone: str | tzinfo | None = None ) -> Self:

        return cls.today(zone).add(days=-1)

    @classmethod
    def of (
        cls, year: int, month: int = 1, day: int = 1, hour: int = 0, minute: int = 0, second: int = 0,
        microsecond: int = 0, zone: str | tzinfo | None = None,
    ) -> Self:

        try: return cls(datetime(year, month, day, hour, minute, second, microsecond, tzinfo=zone_of(zone)))
        except ValueError as error: raise Fault(Code.BAD_REQUEST, reason="date.of") from error

    @classmethod
    def from_stamp ( cls, stamp: float, zone: str | tzinfo | None = None ) -> Self:

        return cls(datetime.fromtimestamp(stamp, zone_of(zone)))

    @classmethod
    def from_format ( cls, text: str, pattern: str, zone: str | tzinfo | None = None ) -> Self:

        return cls(formatter.read(text, pattern, zone_of(zone)))

    @classmethod
    def wrap ( cls, value: object, zone: str | tzinfo | None = None ) -> Self:

        if isinstance(value, Moment): return cls(value.at)
        if isinstance(value, datetime): return cls(aware(value, zone_of(zone)))
        if isinstance(value, calendar): return cls(datetime(value.year, value.month, value.day, tzinfo=zone_of(zone)))
        if isinstance(value, int | float) and not isinstance(value, bool): return cls.from_stamp(float(value), zone)
        if isinstance(value, str): return cls.parse(value, zone)
        if value is None: return cls.now(zone)

        raise Fault(Code.BAD_REQUEST, reason="moment")

    @classmethod
    def parse ( cls, text: str, zone: str | tzinfo | None = None ) -> Self:

        clean = text.strip()
        tz    = zone_of(zone)
        word  = clean.lower()

        if word in WORDS: return cls.today(tz).add(days=WORDS[word]) if word != "now" else cls.now(tz)
        if word[:1] in "+-" and len(word) > 1:

            try: return cls.now(tz).shift(Duration.parse(word[1:]).scaled(-1 if word[0] == "-" else 1))
            except (Fault, ValueError) as error: raise Fault(Code.BAD_REQUEST, reason=f"moment.{text}") from error

        if clean.lstrip("-").replace(".", "", 1).isdigit(): return cls.from_stamp(float(clean), tz)

        try: parsed = datetime.fromisoformat(clean)
        except ValueError:

            spoken = natural.parse(clean, cls.now(tz), tz)

            if spoken is None: raise Fault(Code.BAD_REQUEST, reason=f"moment.{text}") from None

            return cls(spoken.at)

        return cls(aware(parsed, tz))

    def to ( self, zone: str | tzinfo ) -> Self:

        return type(self)(self.at.astimezone(zone_of(zone)))

    def utc ( self ) -> Self:

        return self.to(UTC)

    def add ( self, **shifts: int ) -> Self:

        unknown = set(shifts) - set(SHIFTS)

        if unknown: raise Fault(Code.BAD_REQUEST, reason=f"date.shift.{min(unknown)}")

        moved = self.at

        if shifts.get("years") or shifts.get("months"):

            total = moved.year * MONTHS + (moved.month - 1) + shifts.get("years", 0) * MONTHS + shifts.get("months", 0)
            year, month = divmod(total, MONTHS)
            last  = months.monthrange(year, month + 1)[1]
            moved = moved.replace(year=year, month=month + 1, day=min(moved.day, last))

        delta = timedelta(**{ unit: amount for unit, amount in shifts.items() if unit not in ("years", "months") })

        return type(self)(moved + delta)

    def sub ( self, **shifts: int ) -> Self:

        return self.add(**{ unit: -amount for unit, amount in shifts.items() })

    def shift ( self, duration: Duration ) -> Self:

        return type(self)(self.at + duration.timedelta())

    def diff ( self, other: Moment | None = None ) -> Duration:

        return Duration((other or Moment.now()).at.timestamp() - self.at.timestamp())

    def since ( self, other: Moment | None = None ) -> Duration:

        return Duration(self.at.timestamp() - (other or Moment.now()).at.timestamp())

    def human (
        self, other: Moment | None = None, short: bool = False, locale: str = "en", absolute: bool = False,
    ) -> str:

        return human.relative(self.since(other).total, short, locale, absolute)

    def calendar ( self, other: Moment | None = None, locale: str = "en" ) -> str:

        reference = (other or Moment.now(self.at.tzinfo)).to(self.at.tzinfo or UTC)

        return human.calendar(self.at, reference.at, locale)

    def iso ( self ) -> str:

        return self.utc().at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def date ( self ) -> str:

        return self.at.date().isoformat()

    def time ( self ) -> str:

        return self.at.time().isoformat(timespec="seconds")

    def format ( self, pattern: str = "YYYY-MM-DD HH:mm:ss", locale: str = "en" ) -> str:

        return formatter.format(self.at, pattern, locale)

    def strftime ( self, pattern: str ) -> str:

        return self.at.strftime(pattern)

    def naive ( self ) -> datetime:

        return self.at.replace(tzinfo=None)

    def dump ( self ) -> str:

        return self.iso()

    def describe ( self ) -> dict[str, Any]:

        return {
            "iso": self.iso(), "stamp": self.stamp(), "zone": self.zone(), "weekday": self.weekday(),
            "quarter": self.quarter(),
        }

    def tick ( self ) -> float:

        return time.perf_counter()

    @override
    def __str__ ( self ) -> str:

        return self.iso()

    @override
    def __hash__ ( self ) -> int:

        return hash(self.at)
