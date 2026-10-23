from datetime import UTC, datetime, timedelta
from typing import Self

from engine.error import Code, Fault
from .calendar import Calendar
from .clock import Parts, clock
import calendar as months

SIZES  = { "second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800 }
SPANS  = { "month": 1, "quarter": 3, "year": 12 }
MONTHS = 12

def months_between ( start: datetime, end: datetime ) -> int:

    count = (end.year - start.year) * MONTHS + end.month - start.month

    if count > 0 and (end.day, end.time()) < (start.day, start.time()): count -= 1
    if count < 0 and (end.day, end.time()) > (start.day, start.time()): count += 1

    return count

class Compare(Calendar):

    def midnight ( self, at: datetime ) -> datetime:

        return at.replace(hour=0, minute=0, second=0, microsecond=0)

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
            case _:         raise Fault(Code.BAD_REQUEST, reason="date.unit")

        return self.rebuilt(at)

    def end_of ( self, unit: str ) -> Self:

        start = self.start_of(unit).at

        match unit:
            case "second":  return self.rebuilt(start + timedelta(microseconds=999999))
            case "minute":  return self.rebuilt(start + timedelta(seconds=59, microseconds=999999))
            case "hour":    return self.rebuilt(start + timedelta(hours=1, microseconds=-1))
            case "day":     return self.rebuilt(start + timedelta(days=1, microseconds=-1))
            case "week":    return self.rebuilt(start + timedelta(weeks=1, microseconds=-1))
            case _:         return self.rebuilt(self.month_end(start, SPANS[unit]))

    def month_end ( self, start: datetime, span: int ) -> datetime:

        total       = start.year * MONTHS + start.month - 1 + span - 1
        year, month = divmod(total, MONTHS)
        last        = months.monthrange(year, month + 1)[1]

        return start.replace(year=year, month=month + 1, day=last, hour=23, minute=59, second=59, microsecond=999999)

    def diff_in ( self, unit: str, other: Parts | None = None, absolute: bool = True ) -> int:

        target = other.at if other is not None else clock.now(self.at.tzinfo)

        if unit in SIZES: count = int((target - self.at).total_seconds() / SIZES[unit])
        elif unit in SPANS: count = int(months_between(self.at, target) / SPANS[unit])
        else: raise Fault(Code.BAD_REQUEST, reason="date.unit")

        return abs(count) if absolute else count

    def is_past ( self ) -> bool:

        return self.at < clock.now(self.at.tzinfo)

    def is_future ( self ) -> bool:

        return self.at > clock.now(self.at.tzinfo)

    def is_same ( self, other: Parts, unit: str = "day" ) -> bool:

        shifted = self.rebuilt(other.at.astimezone(self.at.tzinfo or UTC))

        return self.start_of(unit).at == shifted.start_of(unit).at

    def is_today ( self ) -> bool:

        return self.at.date() == clock.now(self.at.tzinfo).date()

    def is_yesterday ( self ) -> bool:

        return self.at.date() == (clock.now(self.at.tzinfo) - timedelta(days=1)).date()

    def is_tomorrow ( self ) -> bool:

        return self.at.date() == (clock.now(self.at.tzinfo) + timedelta(days=1)).date()

    def is_birthday ( self, other: Parts | None = None ) -> bool:

        target = other.at if other is not None else clock.now(self.at.tzinfo)

        return (self.at.month, self.at.day) == (target.month, target.day)

    def is_leap_year ( self ) -> bool:

        return months.isleap(self.at.year)

    def is_start_of_day ( self ) -> bool:

        return self.at == self.midnight(self.at)

    def is_end_of_day ( self ) -> bool:

        return (self.at.hour, self.at.minute, self.at.second) == (23, 59, 59)

    def is_between ( self, start: Parts, end: Parts, inclusive: bool = True ) -> bool:

        return start.at <= self.at <= end.at if inclusive else start.at < self.at < end.at

    def before ( self, other: Parts ) -> bool:

        return self.at < other.at

    def after ( self, other: Parts ) -> bool:

        return self.at > other.at

    def equals ( self, other: Parts ) -> bool:

        return self.at == other.at

    def closest[P: Parts] ( self, *others: P ) -> P:

        if not others: raise Fault(Code.BAD_REQUEST, reason="date.closest")

        return min(others, key=lambda other: abs(other.at.timestamp() - self.at.timestamp()))

    def farthest[P: Parts] ( self, *others: P ) -> P:

        if not others: raise Fault(Code.BAD_REQUEST, reason="date.farthest")

        return max(others, key=lambda other: abs(other.at.timestamp() - self.at.timestamp()))

    def average ( self, other: Parts ) -> Self:

        return self.rebuilt(self.at + (other.at - self.at) / 2)
