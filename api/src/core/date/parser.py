from datetime import datetime, timedelta, tzinfo
from typing import Any

from .calendar import DAYS, weekday_index
import re

UNITS    = {
    "second": "seconds", "minute": "minutes", "hour": "hours", "day": "days", "week": "weeks", "month": "months",
    "year": "years",
}
NUMBERS  = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10,
}
AMOUNT   = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten)"
DAYNAMES = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun"
NAMES    = rf"(week|month|year|quarter|{DAYNAMES})"
RELATIVE = re.compile(rf"^(?:in\s+)?{AMOUNT}\s+(second|minute|hour|day|week|month|year)s?(?:\s+(ago|from now))?$")
NEXT     = re.compile(rf"^(next|last|this)\s+{NAMES}$")
EDGE     = re.compile(r"^(start|end|beginning)\s+of\s+(day|week|month|quarter|year|today|tomorrow|yesterday)$")
CLOCK    = re.compile(r"^(.*?)\s*(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")
WEEKDAY  = re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)$")
NOON     = { "noon": (12, 0), "midnight": (0, 0), "midday": (12, 0) }
DAYWORDS = { "now": 0, "today": 0, "tomorrow": 1, "yesterday": -1 }
HALF     = 12
FORMATS  = (
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %B %Y", "%B %d %Y", "%d %b %Y", "%b %d %Y",
    "%B %d", "%d %B",
)

class Parser:

    def parse ( self, text: str, now: Any, zone: tzinfo ) -> Any | None:

        phrase = " ".join(text.strip().lower().split())

        if not phrase: return None

        base, clock = self.split_clock(phrase)
        moment      = self.day_phrase(base, now, zone) if base else now.start_of("day")

        if moment is None: return None
        if clock is not None: moment = moment.set(hour=clock[0], minute=clock[1], second=0, microsecond=0)

        return moment

    def split_clock ( self, phrase: str ) -> tuple[str, tuple[int, int] | None]:

        for word, clock in NOON.items():
            if phrase.endswith(word): return phrase[:-len(word)].rstrip(" at"), clock

        matched = CLOCK.match(phrase)

        if matched is None or RELATIVE.match(phrase) or matched.group(2) is None: return phrase, None
        if matched.group(3) is None and matched.group(4) is None: return phrase, None

        hour   = int(matched.group(2)) % HALF if matched.group(4) else int(matched.group(2))
        hour  += HALF if matched.group(4) == "pm" else 0
        minute = int(matched.group(3) or 0)

        return matched.group(1).strip(), (hour, minute)

    def day_phrase ( self, phrase: str, now: Any, zone: tzinfo ) -> Any | None:

        today = now.start_of("day")

        if phrase in DAYWORDS: return now if phrase == "now" else today.add(days=DAYWORDS[phrase])
        if WEEKDAY.match(phrase): return today if today.at.weekday() == weekday_index(phrase) else today.next(phrase)

        relative = RELATIVE.match(phrase)

        if relative: return self.relative(relative, now)

        leap = NEXT.match(phrase)

        if leap: return self.leap(leap, now)

        edge = EDGE.match(phrase)

        if edge: return self.edge(edge, now)

        return self.absolute(phrase, now, zone)

    def relative ( self, matched: re.Match[str], now: Any ) -> Any:

        amount = NUMBERS.get(matched.group(1)) or int(matched.group(1))
        unit   = UNITS[matched.group(2)]
        sign   = -1 if matched.group(3) == "ago" else 1

        return now.add(**{ unit: sign * amount })

    def leap ( self, matched: re.Match[str], now: Any ) -> Any:

        direction, unit = matched.group(1), matched.group(2)
        today           = now.start_of("day")

        if unit in ("week", "month", "year", "quarter"):

            if direction == "this": return today.start_of(unit)

            step    = { "months": 3 } if unit == "quarter" else { f"{unit}s": 1 }
            shifted = today.add(**step) if direction == "next" else today.sub(**step)

            return shifted.start_of(unit)

        if direction == "next": return today.next(unit)
        if direction == "last": return today.previous(unit)

        return today if today.at.weekday() == weekday_index(unit) else today.next(unit)

    def edge ( self, matched: re.Match[str], now: Any ) -> Any:

        side, unit = matched.group(1), matched.group(2)
        anchor     = now.start_of("day").add(days=DAYWORDS.get(unit, 0)) if unit in DAYWORDS else now
        target     = "day" if unit in DAYWORDS else unit

        return anchor.end_of(target) if side == "end" else anchor.start_of(target)

    def absolute ( self, phrase: str, now: Any, zone: tzinfo ) -> Any | None:

        for pattern in FORMATS:

            try: parsed = datetime.strptime(phrase, pattern)
            except ValueError: continue

            if "%Y" not in pattern: parsed = parsed.replace(year=now.at.year)

            return type(now)(parsed.replace(tzinfo=zone))

        return None

    def weekdays ( self ) -> tuple[str, ...]:

        return DAYS

    def shift_text ( self, delta: timedelta ) -> str:

        seconds = int(delta.total_seconds())
        sign    = "-" if seconds < 0 else "+"

        return f"{sign}{abs(seconds)}s"
