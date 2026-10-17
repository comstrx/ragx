from datetime import UTC, datetime, timedelta

from .date import Date

DateTime  = datetime
TimeDelta = timedelta
date      = Date()

__all__ = ["UTC", "Date", "DateTime", "TimeDelta", "date"]
