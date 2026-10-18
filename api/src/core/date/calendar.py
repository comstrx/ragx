from datetime import date as calendar, datetime, timedelta
from typing import Any, Self

import calendar as months

DAYS     = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SATURDAY = 5
WEEK     = 7
UNITS    = { "minute": 60, "hour": 3600, "day": 86400 }

def weekday_index ( day: str | int ) -> int:

    if isinstance(day, int):

        if not 0 <= day < WEEK: raise ValueError(day)

        return day

    wanted = day.strip().lower()
    index  = next((position for position, name in enumerate(DAYS) if wanted and name.startswith(wanted)), None)

    if index is None: raise ValueError(day)

    return index

class Calendar:

    at: datetime

    weekday_index = staticmethod(weekday_index)

    def __init__ ( self, at: datetime ) -> None:

        self.at = at

    def rebuilt ( self, at: datetime ) -> Self:
        return type(self)(at)

    def day_name ( self, short: bool = False ) -> str:

        name = DAYS[self.at.weekday()].capitalize()

        return name[:3] if short else name

    def month_name ( self, short: bool = False ) -> str:

        name = months.month_name[self.at.month]

        return name[:3] if short else name

    def is_business_day ( self, holidays: set[calendar] | None = None ) -> bool:
        return self.at.weekday() < SATURDAY and self.at.date() not in (holidays or set())

    def add_business_days ( self, count: int, holidays: set[calendar] | None = None ) -> Self:

        step   = 1 if count >= 0 else -1
        left   = abs(count)
        cursor = self.at

        while left > 0:

            cursor += timedelta(days=step)

            if cursor.weekday() < SATURDAY and cursor.date() not in (holidays or set()): left -= 1

        return self.rebuilt(cursor)

    def business_days_until ( self, other: Any, holidays: set[calendar] | None = None ) -> int:

        start, end = sorted((self.at.date(), other.at.date()))
        sign       = 1 if other.at >= self.at else -1
        count      = 0
        cursor     = start

        while cursor < end:

            cursor += timedelta(days=1)

            if cursor.weekday() < SATURDAY and cursor not in (holidays or set()): count += 1

        return count * sign

    def next ( self, day: str | int ) -> Self:

        wanted = weekday_index(day)
        ahead  = (wanted - self.at.weekday() - 1) % WEEK + 1

        return self.rebuilt(self.at + timedelta(days=ahead))

    def previous ( self, day: str | int ) -> Self:

        wanted = weekday_index(day)
        back   = (self.at.weekday() - wanted - 1) % WEEK + 1

        return self.rebuilt(self.at - timedelta(days=back))

    def nth_of_month ( self, nth: int, day: str | int ) -> Self | None:

        wanted = weekday_index(day)
        first  = self.at.replace(day=1)
        offset = (wanted - first.weekday()) % WEEK
        target = 1 + offset + (nth - 1) * WEEK

        if target > months.monthrange(first.year, first.month)[1]: return None

        return self.rebuilt(first.replace(day=target))

    def first_of_month ( self, day: str | int ) -> Self:

        found = self.nth_of_month(1, day)

        if found is None: raise ValueError(day)

        return found

    def last_of_month ( self, day: str | int ) -> Self:

        last   = self.at.replace(day=months.monthrange(self.at.year, self.at.month)[1])
        back   = (last.weekday() - weekday_index(day)) % WEEK

        return self.rebuilt(last - timedelta(days=back))

    def is_last_of_month ( self ) -> bool:
        return self.at.day == months.monthrange(self.at.year, self.at.month)[1]

    def is_first_of_month ( self ) -> bool:
        return self.at.day == 1

    def is_dst ( self ) -> bool:

        offset = self.at.dst()

        return bool(offset) and offset != timedelta(0)

    def week_of_month ( self ) -> int:
        return (self.at.day + self.at.replace(day=1).weekday() - 1) // WEEK + 1

    def age ( self, today: Any = None ) -> int:

        now    = (today.at if today is not None else datetime.now(self.at.tzinfo)).date()
        born   = self.at.date()
        passed = (now.month, now.day) >= (born.month, born.day)

        return now.year - born.year - (0 if passed else 1)

    def set ( self, **fields: int ) -> Self:

        changes: Any = fields

        return self.rebuilt(self.at.replace(**changes))

    def floor ( self, unit: str ) -> Self:

        size = UNITS.get(unit)

        if size is None: raise ValueError(unit)

        stamp = self.at.timestamp()

        return self.rebuilt(datetime.fromtimestamp(stamp - stamp % size, self.at.tzinfo))

    def round ( self, unit: str ) -> Self:

        size = UNITS.get(unit)

        if size is None: raise ValueError(unit)

        stamp = self.at.timestamp()

        return self.rebuilt(datetime.fromtimestamp(round(stamp / size) * size, self.at.tzinfo))

    def ceil ( self, unit: str ) -> Self:

        size = UNITS.get(unit)

        if size is None: raise ValueError(unit)

        stamp = self.at.timestamp()
        over  = stamp % size

        return self.rebuilt(datetime.fromtimestamp(stamp - over + (size if over else 0), self.at.tzinfo))

    def stamp_ms ( self ) -> int:
        return int(self.at.timestamp() * 1000)

    def to_date_string ( self ) -> str:
        return self.at.date().isoformat()

    def to_time_string ( self ) -> str:
        return self.at.strftime("%H:%M:%S")

    def to_datetime_string ( self ) -> str:
        return self.at.strftime("%Y-%m-%d %H:%M:%S")

    def calendar_week ( self ) -> tuple[int, int]:

        year, week, _ = self.at.isocalendar()

        return year, week
