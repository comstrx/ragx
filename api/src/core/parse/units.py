from decimal import Decimal, InvalidOperation
import re

DURATION = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?|d|days?|w|weeks?)",
    re.IGNORECASE,
)
SIZE     = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtp]?i?b?)\s*$", re.IGNORECASE)
RATE     = re.compile(r"^\s*(\d+)\s*/\s*(second|sec|s|minute|min|m|hour|hr|h|day|d)s?\s*$", re.IGNORECASE)
SECONDS  = {
    "ms": 0.001, "millisecond": 0.001, "milliseconds": 0.001,
    "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0,
    "m": 60.0, "min": 60.0, "mins": 60.0, "minute": 60.0, "minutes": 60.0,
    "h": 3600.0, "hr": 3600.0, "hrs": 3600.0, "hour": 3600.0, "hours": 3600.0,
    "d": 86400.0, "day": 86400.0, "days": 86400.0,
    "w": 604800.0, "week": 604800.0, "weeks": 604800.0,
}
WINDOWS  = {
    "second": 1.0, "sec": 1.0, "s": 1.0, "minute": 60.0, "min": 60.0, "m": 60.0,
    "hour": 3600.0, "hr": 3600.0, "h": 3600.0, "day": 86400.0, "d": 86400.0,
}
KILO     = 1024
PREFIXES = "kmgtp"
PAIR     = 2

class Units:

    def duration ( self, value: object, default: float = 0.0 ) -> float:

        if isinstance(value, int | float) and not isinstance(value, bool): return float(value)
        if not isinstance(value, str): return default

        text = value.strip()

        if not text: return default

        try: return float(text)
        except ValueError: pass

        found = DURATION.findall(text)

        if not found or DURATION.sub("", text).strip(" ,and") != "": return default

        return sum(float(amount) * SECONDS[unit.lower()] for amount, unit in found)

    def bytes ( self, value: object, default: int = 0 ) -> int:

        if isinstance(value, int) and not isinstance(value, bool): return value
        if not isinstance(value, str): return default

        matched = SIZE.match(value)

        if matched is None: return default

        amount = Decimal(matched.group(1))
        unit   = matched.group(2).lower()
        power  = PREFIXES.index(unit[0]) + 1 if unit and unit[0] in PREFIXES else 0
        base   = 1000 if unit and "i" not in unit and power and len(unit) == PAIR and unit.endswith("b") else KILO

        return int(amount * (base ** power))

    def rate ( self, value: str ) -> tuple[int, float]:

        matched = RATE.match(value)

        if matched is None: raise ValueError(value)

        return int(matched.group(1)), WINDOWS[matched.group(2).lower()]

    def percent ( self, value: object, default: float = 0.0 ) -> float:

        if isinstance(value, int | float) and not isinstance(value, bool): return float(value)
        if not isinstance(value, str): return default

        text = value.strip().rstrip("%").strip()

        try: return float(Decimal(text))
        except (InvalidOperation, ValueError): return default

    def ratio ( self, value: object, default: float = 0.0 ) -> float:

        text = value.strip() if isinstance(value, str) else value

        if isinstance(text, str) and text.endswith("%"): return self.percent(text, default * 100) / 100

        return self.percent(text, default)

    def span ( self, value: object ) -> tuple[int, int] | None:

        if not isinstance(value, str): return None

        first, dash, last = value.strip().partition("-")

        if not dash or not first.strip().isdigit() or not last.strip().isdigit(): return None

        return int(first), int(last)
