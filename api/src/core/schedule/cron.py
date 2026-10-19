from datetime import datetime, timedelta
from typing import Any

from core.error import Code, Fault

ALIASES = {
    "@yearly"   : "0 0 1 1 *",
    "@annually" : "0 0 1 1 *",
    "@monthly"  : "0 0 1 * *",
    "@weekly"   : "0 0 * * 0",
    "@daily"    : "0 0 * * *",
    "@midnight" : "0 0 * * *",
    "@hourly"   : "0 * * * *",
}
FIELDS  = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("weekday", 0, 6))
SUNDAY  = 7
HORIZON = 366 * 5
NAMES   = { "sun": "0", "mon": "1", "tue": "2", "wed": "3", "thu": "4", "fri": "5", "sat": "6" }
MONTHS  = {
    "jan": "1", "feb": "2", "mar": "3", "apr": "4", "may": "5", "jun": "6",
    "jul": "7", "aug": "8", "sep": "9", "oct": "10", "nov": "11", "dec": "12",
}

class Cron:

    def __init__ ( self, expression: str ) -> None:

        parts = ALIASES.get(expression.strip().lower(), expression).split()

        if len(parts) != len(FIELDS): raise Fault(Code.INTERNAL, reason="cron.fields")

        self.expression = expression
        self.parts      = [self.words(part, index) for index, part in enumerate(parts)]
        self.minutes    = self.field(self.parts[0], *FIELDS[0][1:])
        self.hours      = self.field(self.parts[1], *FIELDS[1][1:])
        self.days       = self.field(self.parts[2], *FIELDS[2][1:])
        self.months     = self.field(self.parts[3], *FIELDS[3][1:])
        self.weekdays   = frozenset(0 if day == SUNDAY else day for day in self.field(self.parts[4], 0, SUNDAY))
        self.any_day    = self.parts[2] == "*"
        self.any_week   = self.parts[4] == "*"

    def words ( self, part: str, index: int ) -> str:

        lowered = part.lower()
        table   = NAMES if index == len(FIELDS) - 1 else MONTHS if index == len(FIELDS) - 2 else {}

        for name, number in table.items(): lowered = lowered.replace(name, number)

        return lowered

    def field ( self, text: str, low: int, high: int ) -> frozenset[int]:

        values: set[int] = set()

        for piece in text.split(","):

            span, _, step = piece.partition("/")
            stride        = int(step) if step else 1
            start, end    = self.bounds(span, low, high)

            if stride < 1 or start < low or end > high or start > end: raise Fault(Code.INTERNAL, reason="cron.range")

            values.update(range(start, end + 1, stride))

        return frozenset(values)

    def bounds ( self, span: str, low: int, high: int ) -> tuple[int, int]:

        if span == "*": return low, high
        if "-" in span:

            first, last = span.split("-", 1)

            return int(first), int(last)

        return int(span), int(span)

    def day_matches ( self, moment: datetime ) -> bool:

        weekday = (moment.weekday() + 1) % SUNDAY

        if moment.month not in self.months: return False
        if self.any_day and self.any_week: return True
        if self.any_day: return weekday in self.weekdays
        if self.any_week: return moment.day in self.days

        return moment.day in self.days or weekday in self.weekdays

    def matches ( self, moment: datetime ) -> bool:

        return moment.minute in self.minutes and moment.hour in self.hours and self.day_matches(moment)

    def next ( self, after: datetime ) -> datetime:

        moment = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

        for _ in range(HORIZON):

            if self.day_matches(moment):

                found = self.slot(moment)

                if found is not None: return found

            moment = (moment + timedelta(days=1)).replace(hour=0, minute=0)

        raise Fault(Code.INTERNAL, reason="cron.unreachable")

    def slot ( self, moment: datetime ) -> datetime | None:

        for hour in sorted(self.hours):

            if hour < moment.hour: continue

            for minute in sorted(self.minutes):

                if hour == moment.hour and minute < moment.minute: continue

                return moment.replace(hour=hour, minute=minute)

        return None

    def upcoming ( self, after: datetime, count: int = 5 ) -> list[datetime]:

        found: list[datetime] = []
        cursor = after

        for _ in range(max(count, 0)):

            cursor = self.next(cursor)

            found.append(cursor)

        return found

    def with_weekdays ( self, weekdays: str ) -> Cron:

        return Cron(" ".join([*self.parts[:4], weekdays]))

    def describe ( self ) -> dict[str, Any]:

        return {
            "expression": self.expression, "minutes": sorted(self.minutes), "hours": sorted(self.hours),
            "days": "*" if self.any_day else sorted(self.days), "months": sorted(self.months),
            "weekdays": "*" if self.any_week else sorted(self.weekdays),
        }
