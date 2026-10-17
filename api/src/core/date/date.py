from datetime import UTC, datetime, timedelta
import time

class Date:

    def now ( self ) -> datetime:
        return datetime.now(UTC)

    def stamp ( self ) -> float:
        return time.time()

    def tick ( self ) -> float:
        return time.perf_counter()

    def iso ( self, moment: datetime ) -> str:
        return self.utc(moment).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def utc ( self, moment: datetime ) -> datetime:
        return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)

    def parse ( self, text: str ) -> datetime:
        return self.utc(datetime.fromisoformat(text))

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
