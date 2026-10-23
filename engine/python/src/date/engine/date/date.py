from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import available_timezones

from engine.error import Fault
from .calendar import Calendar
from .clock import clock, zone_of
from .duration import Duration
from .format import Formatter
from .moment import Moment
from .period import Period
import time

class Date:

    def __init__ ( self ) -> None:

        self._format = Formatter()

    def now ( self ) -> datetime:

        return clock.utc()

    def stamp ( self ) -> float:

        return clock.stamp()

    def freeze ( self, at: object = None, ticking: bool = False ) -> Moment:

        return Moment(clock.freeze(None if at is None else Moment.wrap(at).at, ticking))

    def travel ( self, **units: float ) -> Moment:

        return Moment(clock.travel(**units))

    def thaw ( self ) -> None:

        clock.thaw()

    @contextmanager
    def frozen ( self, at: object = None, ticking: bool = False ) -> Iterator[Moment]:

        with clock.at(None if at is None else Moment.wrap(at).at, ticking) as moment: yield Moment(moment)

    def weekend ( self, *days: str | int ) -> frozenset[int]:

        return Calendar.use_weekend(*days) if days else Calendar.weekend

    def tick ( self ) -> float:

        return time.perf_counter()

    def iso ( self, moment: datetime ) -> str:

        return self.utc(moment).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def utc ( self, moment: datetime ) -> datetime:

        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)

    def parse ( self, text: str ) -> datetime:

        return Moment.parse(text).utc().at

    def since ( self, moment: datetime ) -> float:

        return (self.now() - self.utc(moment)).total_seconds()

    def elapsed ( self, started: float ) -> float:

        return round((time.perf_counter() - started) * 1000, 2)

    def add (
        self, moment: datetime, seconds: float = 0, minutes: float = 0, hours: float = 0, days: float = 0,
    ) -> datetime:

        return moment + timedelta(seconds=seconds, minutes=minutes, hours=hours, days=days)

    def start_of_day ( self, moment: datetime ) -> datetime:

        return self.utc(moment).replace(hour=0, minute=0, second=0, microsecond=0)

    def end_of_day ( self, moment: datetime ) -> datetime:

        return self.utc(moment).replace(hour=23, minute=59, second=59, microsecond=999999)

    def between ( self, moment: datetime, start: datetime, end: datetime ) -> bool:

        return self.utc(start) <= self.utc(moment) <= self.utc(end)

    def from_stamp ( self, stamp: float ) -> datetime:

        return datetime.fromtimestamp(stamp, UTC)

    def moment ( self, value: object = None, zone: str | tzinfo | None = None ) -> Moment:

        return Moment.wrap(value, zone)

    def today ( self, zone: str | tzinfo | None = None ) -> Moment:

        return Moment.today(zone)

    def tomorrow ( self, zone: str | tzinfo | None = None ) -> Moment:

        return Moment.tomorrow(zone)

    def yesterday ( self, zone: str | tzinfo | None = None ) -> Moment:

        return Moment.yesterday(zone)

    def duration ( self, value: object = 0.0, **units: float ) -> Duration:

        return Duration.of(**units) if units else Duration.parse(value)

    def period ( self, start: object, end: object ) -> Period:

        return Period.of(start, end)

    def zone ( self, name: str | tzinfo | None ) -> tzinfo:

        return zone_of(name)

    def format ( self, moment: datetime | Moment, pattern: str = "YYYY-MM-DD HH:mm:ss", locale: str = "en" ) -> str:

        return self._format.format(moment.at if isinstance(moment, Moment) else moment, pattern, locale)

    def human ( self, moment: datetime | Moment, short: bool = False, locale: str = "en" ) -> str:

        return Moment.wrap(moment).human(short=short, locale=locale)

    def span ( self, seconds: float, short: bool = False, locale: str = "en" ) -> str:

        return self._format.span(seconds, short, locale)

    def age ( self, birth: datetime | Moment, today: datetime | Moment | None = None ) -> int:

        return Moment.wrap(birth).age(Moment.wrap(today) if today is not None else None)

    def is_leap ( self, year: int ) -> bool:

        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def days_in ( self, year: int, month: int ) -> int:

        return Moment.of(year, month).days_in_month()

    def business_days ( self, start: datetime | Moment, end: datetime | Moment ) -> int:

        return Moment.wrap(start).business_days_until(Moment.wrap(end))

    def zones ( self ) -> list[str]:

        return sorted(available_timezones())

    def is_valid ( self, text: str ) -> bool:

        try: Moment.parse(text)
        except Fault: return False

        return True
