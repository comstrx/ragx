from dataclasses import dataclass
from datetime import UTC, date as calendar, datetime, timedelta, tzinfo
from typing import Any, Self
from zoneinfo import ZoneInfo

from core.error import Code, Fault
from .calendar import Calendar
from .duration import Duration
from .format import Formatter
from .parser import Parser
import calendar as months, time

UNITS     = ("second", "minute", "hour", "day", "week", "month", "quarter", "year")
FRIDAY    = 5
MONTHS    = 12
SHIFTS    = ("years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds")
WORDS     = { "now": 0, "today": 0, "tomorrow": 1, "yesterday": -1 }
formatter = Formatter()
natural   = Parser()

def zone_of ( zone: str | tzinfo | None ) -> tzinfo:

    if zone is None: return UTC
    if isinstance(zone, tzinfo): return zone

    try: return UTC if zone.upper() == "UTC" else ZoneInfo(zone)
    except (KeyError, ValueError) as error: raise Fault(Code.BAD_REQUEST, reason=f"zone.{zone}") from error

def aware ( moment: datetime, zone: tzinfo ) -> datetime:
    return moment.replace(tzinfo=zone) if moment.tzinfo is None else moment

@dataclass(frozen=True, slots=True, order=True)
class Moment(Calendar):

    at: datetime

    @classmethod
    def now ( cls, zone: str | tzinfo | None = None ) -> Self:
        return cls(datetime.now(zone_of(zone)))

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
        return cls(datetime(year, month, day, hour, minute, second, microsecond, tzinfo=zone_of(zone)))

    @classmethod
    def from_stamp ( cls, stamp: float, zone: str | tzinfo | None = None ) -> Self:
        return cls(datetime.fromtimestamp(stamp, zone_of(zone)))

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
            except ValueError as error: raise Fault(Code.BAD_REQUEST, reason=f"moment.{text}") from error

        if clean.lstrip("-").replace(".", "", 1).isdigit(): return cls.from_stamp(float(clean), tz)

        try: parsed = datetime.fromisoformat(clean)
        except ValueError:

            spoken = natural.parse(clean, cls.now(tz), tz)

            if spoken is None: raise Fault(Code.BAD_REQUEST, reason=f"moment.{text}") from None

            return cls(spoken.at)

        return cls(aware(parsed, tz))

    def year ( self ) -> int:
        return self.at.year

    def month ( self ) -> int:
        return self.at.month

    def day ( self ) -> int:
        return self.at.day

    def hour ( self ) -> int:
        return self.at.hour

    def minute ( self ) -> int:
        return self.at.minute

    def second ( self ) -> int:
        return self.at.second

    def weekday ( self ) -> int:
        return self.at.isoweekday()

    def day_of_year ( self ) -> int:
        return self.at.timetuple().tm_yday

    def week ( self ) -> int:
        return self.at.isocalendar().week

    def quarter ( self ) -> int:
        return (self.at.month - 1) // 3 + 1

    def days_in_month ( self ) -> int:
        return months.monthrange(self.at.year, self.at.month)[1]

    def zone ( self ) -> str:
        return str(self.at.tzinfo)

    def stamp ( self ) -> float:
        return self.at.timestamp()

    def to ( self, zone: str | tzinfo ) -> Self:
        return type(self)(self.at.astimezone(zone_of(zone)))

    def utc ( self ) -> Self:
        return self.to(UTC)

    def add ( self, **shifts: int ) -> Self:

        unknown = set(shifts) - set(SHIFTS)

        if unknown: raise ValueError(sorted(unknown))

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

    def start_of ( self, unit: str ) -> Self:

        at = self.at

        match unit:
            case "second":  at = at.replace(microsecond=0)
            case "minute":  at = at.replace(second=0, microsecond=0)
            case "hour":    at = at.replace(minute=0, second=0, microsecond=0)
            case "day":     at = self.midnight(at)
            case "week":    at = self.midnight(at - timedelta(days=at.weekday()))
            case "month":   at = self.midnight(at.replace(day=1))
            case "quarter": at = self.midnight(at.replace(month=(self.quarter() - 1) * 3 + 1, day=1))
            case "year":    at = self.midnight(at.replace(month=1, day=1))
            case _:         raise ValueError(unit)

        return type(self)(at)

    def midnight ( self, at: datetime ) -> datetime:
        return at.replace(hour=0, minute=0, second=0, microsecond=0)

    def end_of ( self, unit: str ) -> Self:

        shifts: dict[str, dict[str, int]] = {
            "second": {}, "minute": {}, "hour": { "hours": 1 }, "day": { "days": 1 }, "week": { "weeks": 1 },
            "month": { "months": 1 }, "quarter": { "months": 3 }, "year": { "years": 1 },
        }

        if unit not in shifts: raise ValueError(unit)
        if unit == "second": return type(self)(self.at.replace(microsecond=999999))
        if unit == "minute": return type(self)(self.at.replace(second=59, microsecond=999999))

        return self.start_of(unit).add(**shifts[unit]).add(microseconds=-1)

    def diff ( self, other: Moment | None = None ) -> Duration:
        return Duration((other or Moment.now()).at.timestamp() - self.at.timestamp())

    def since ( self, other: Moment | None = None ) -> Duration:
        return Duration(self.at.timestamp() - (other or Moment.now()).at.timestamp())

    def human ( self, other: Moment | None = None, short: bool = False ) -> str:
        return formatter.relative(self.since(other).total, short)

    def is_past ( self ) -> bool:
        return self.at < datetime.now(self.at.tzinfo)

    def is_future ( self ) -> bool:
        return self.at > datetime.now(self.at.tzinfo)

    def is_same ( self, other: Moment, unit: str = "day" ) -> bool:
        return self.start_of(unit).at == other.to(self.at.tzinfo or UTC).start_of(unit).at

    def is_today ( self ) -> bool:
        return self.is_same(Moment.now(self.at.tzinfo))

    def is_yesterday ( self ) -> bool:
        return self.is_same(Moment.yesterday(self.at.tzinfo))

    def is_tomorrow ( self ) -> bool:
        return self.is_same(Moment.tomorrow(self.at.tzinfo))

    def is_weekend ( self ) -> bool:
        return self.at.isoweekday() > FRIDAY

    def is_weekday ( self ) -> bool:
        return not self.is_weekend()

    def is_leap_year ( self ) -> bool:
        return months.isleap(self.at.year)

    def is_between ( self, start: Moment, end: Moment, inclusive: bool = True ) -> bool:
        return start.at <= self.at <= end.at if inclusive else start.at < self.at < end.at

    def before ( self, other: Moment ) -> bool:
        return self.at < other.at

    def after ( self, other: Moment ) -> bool:
        return self.at > other.at

    def closest ( self, *others: Moment ) -> Moment:
        return min(others, key=lambda other: abs(other.at.timestamp() - self.at.timestamp()))

    def farthest ( self, *others: Moment ) -> Moment:
        return max(others, key=lambda other: abs(other.at.timestamp() - self.at.timestamp()))

    def iso ( self ) -> str:
        return self.utc().at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def date ( self ) -> str:
        return self.at.date().isoformat()

    def time ( self ) -> str:
        return self.at.time().isoformat(timespec="seconds")

    def format ( self, pattern: str = "YYYY-MM-DD HH:mm:ss" ) -> str:
        return formatter.format(self.at, pattern)

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

    def __str__ ( self ) -> str:
        return self.iso()

    def __hash__ ( self ) -> int:
        return hash(self.at)

    def tick ( self ) -> float:
        return time.perf_counter()
