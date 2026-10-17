from datetime import datetime

from core.exceptions import Code, Fault

ALIASES = {
    "@yearly"   : "0 0 1 1 *",
    "@annually" : "0 0 1 1 *",
    "@monthly"  : "0 0 1 * *",
    "@weekly"   : "0 0 * * 0",
    "@daily"    : "0 0 * * *",
    "@midnight" : "0 0 * * *",
    "@hourly"   : "0 * * * *",
}
FIELDS = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("month", 1, 12), ("weekday", 0, 6))
SUNDAY = 7

class Cron:

    def __init__ ( self, expression: str ) -> None:

        parts = ALIASES.get(expression.strip().lower(), expression).split()

        if len(parts) != len(FIELDS): raise Fault(Code.INTERNAL, reason=f"cron.{expression}")

        self.expression = expression
        self.minutes    = self.field(parts[0], *FIELDS[0][1:])
        self.hours      = self.field(parts[1], *FIELDS[1][1:])
        self.days       = self.field(parts[2], *FIELDS[2][1:])
        self.months     = self.field(parts[3], *FIELDS[3][1:])
        self.weekdays   = frozenset(0 if day == SUNDAY else day for day in self.field(parts[4], 0, SUNDAY))
        self.any_day    = parts[2] == "*"
        self.any_week   = parts[4] == "*"

    def field ( self, text: str, low: int, high: int ) -> frozenset[int]:

        values: set[int] = set()

        for piece in text.split(","):

            span, _, step = piece.partition("/")
            stride        = int(step) if step else 1
            start, end    = self.bounds(span, low, high)

            if stride < 1 or start < low or end > high or start > end: raise Fault(Code.INTERNAL, reason=f"cron.{text}")

            values.update(range(start, end + 1, stride))

        return frozenset(values)

    def bounds ( self, span: str, low: int, high: int ) -> tuple[int, int]:

        if span == "*": return low, high
        if "-" in span:

            first, last = span.split("-", 1)

            return int(first), int(last)

        return int(span), int(span)

    def matches ( self, moment: datetime ) -> bool:

        weekday = (moment.weekday() + 1) % SUNDAY

        if moment.minute not in self.minutes or moment.hour not in self.hours or moment.month not in self.months:
            return False

        if self.any_day and self.any_week: return True
        if self.any_day: return weekday in self.weekdays
        if self.any_week: return moment.day in self.days

        return moment.day in self.days or weekday in self.weekdays
