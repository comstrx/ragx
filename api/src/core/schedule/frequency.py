from datetime import tzinfo
from typing import Self
from zoneinfo import ZoneInfo

from core.date import Calendar
from core.error import Code, Fault
from .cron import Cron

WEEK = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday")

class Frequency:

    def __init__ ( self ) -> None:

        self.cron: Cron | None = None
        self.interval: float | None = None
        self.zone: tzinfo = ZoneInfo("UTC")

    def at ( self, expression: str ) -> Self:

        self.cron     = Cron(expression)
        self.interval = None

        return self

    def cron_expression ( self, expression: str ) -> Self:

        return self.at(expression)

    def every ( self, seconds: float ) -> Self:

        if seconds <= 0: raise Fault(Code.INTERNAL, reason="schedule.interval")

        self.interval = float(seconds)
        self.cron     = None

        return self

    def every_minute ( self ) -> Self:

        return self.at("* * * * *")

    def every_minutes ( self, count: int ) -> Self:

        return self.at(f"*/{count} * * * *")

    def every_five_minutes ( self ) -> Self:

        return self.every_minutes(5)

    def every_ten_minutes ( self ) -> Self:

        return self.every_minutes(10)

    def every_fifteen_minutes ( self ) -> Self:

        return self.every_minutes(15)

    def every_thirty_minutes ( self ) -> Self:

        return self.every_minutes(30)

    def hourly ( self, minute: int = 0 ) -> Self:

        return self.at(f"{minute} * * * *")

    def every_hours ( self, count: int, minute: int = 0 ) -> Self:

        return self.at(f"{minute} */{count} * * *")

    def daily ( self ) -> Self:

        return self.at("0 0 * * *")

    def daily_at ( self, clock: str ) -> Self:

        hour, minute = self.clock(clock)

        return self.at(f"{minute} {hour} * * *")

    def twice_daily ( self, first: int = 1, second: int = 13 ) -> Self:

        return self.at(f"0 {first},{second} * * *")

    def weekly ( self ) -> Self:

        return self.at("0 0 * * 0")

    def weekly_on ( self, day: str | int, clock: str = "00:00" ) -> Self:

        hour, minute = self.clock(clock)
        index        = WEEK.index(day.lower()) if isinstance(day, str) else day

        return self.at(f"{minute} {hour} * * {index}")

    def monthly ( self ) -> Self:

        return self.at("0 0 1 * *")

    def monthly_on ( self, day: int, clock: str = "00:00" ) -> Self:

        hour, minute = self.clock(clock)

        return self.at(f"{minute} {hour} {day} * *")

    def quarterly ( self ) -> Self:

        return self.at("0 0 1 1,4,7,10 *")

    def yearly ( self ) -> Self:

        return self.at("0 0 1 1 *")

    def weekdays ( self ) -> Self:

        return self.days("1-5")

    def weekends ( self ) -> Self:

        return self.days("0,6")

    def on_days ( self, *names: str | int ) -> Self:

        return self.days(",".join(str((Calendar.weekday_index(name) + 1) % 7) for name in names))

    def days ( self, weekdays: str ) -> Self:

        base      = self.cron or Cron("* * * * *")
        self.cron = base.with_weekdays(weekdays)

        return self

    def clock ( self, text: str ) -> tuple[int, int]:

        hour, _, minute = text.partition(":")

        return int(hour), int(minute or 0)

    def timezone ( self, name: str ) -> Self:

        self.zone = ZoneInfo(name)

        return self
