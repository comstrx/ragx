from datetime import datetime
import re

TOKEN   = re.compile(
    r"\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|DDDD|DD|Do|D|dddd|ddd|d|HH|H|hh|h|mm|m|ss|s|SSS|A|a|ZZ|Z|X|x|Q|W|E",
)
SPECIAL = (11, 12, 13)
SUFFIX  = { 1: "st", 2: "nd", 3: "rd" }
MINUTE  = 60
HOUR    = 3600
DAY     = 86400
WEEK    = 604800
MONTH   = 2629800
YEAR    = 31557600
STEPS   = (
    (YEAR, "year"), (MONTH, "month"), (WEEK, "week"), (DAY, "day"), (HOUR, "hour"), (MINUTE, "minute"),
    (1, "second"),
)
JUST    = 5
NOON    = 12

def ordinal ( value: int ) -> str:
    return f"{value}{'th' if value % 100 in SPECIAL else SUFFIX.get(value % 10, 'th')}"

def offset ( moment: datetime, colon: bool ) -> str:

    delta = moment.utcoffset()

    if delta is None: return "+00:00" if colon else "+0000"

    total = int(delta.total_seconds())
    sign  = "-" if total < 0 else "+"
    hours, minutes = divmod(abs(total) // MINUTE, MINUTE)

    return f"{sign}{hours:02d}{':' if colon else ''}{minutes:02d}"

def piece ( moment: datetime, token: str ) -> str:

    match token:
        case "YYYY": return f"{moment.year:04d}"
        case "YY":   return f"{moment.year % 100:02d}"
        case "MMMM": return moment.strftime("%B")
        case "MMM":  return moment.strftime("%b")
        case "MM":   return f"{moment.month:02d}"
        case "M":    return str(moment.month)
        case "DDDD": return f"{moment.timetuple().tm_yday:03d}"
        case "DD":   return f"{moment.day:02d}"
        case "Do":   return ordinal(moment.day)
        case "D":    return str(moment.day)
        case "dddd": return moment.strftime("%A")
        case "ddd":  return moment.strftime("%a")
        case "d":    return str(moment.isoweekday() % 7)
        case "HH":   return f"{moment.hour:02d}"
        case "H":    return str(moment.hour)
        case "hh":   return f"{moment.hour % NOON or NOON:02d}"
        case "h":    return str(moment.hour % NOON or NOON)
        case "mm":   return f"{moment.minute:02d}"
        case "m":    return str(moment.minute)
        case "ss":   return f"{moment.second:02d}"
        case "s":    return str(moment.second)
        case "SSS":  return f"{moment.microsecond // 1000:03d}"
        case "A":    return "AM" if moment.hour < NOON else "PM"
        case "a":    return "am" if moment.hour < NOON else "pm"
        case "ZZ":   return offset(moment, colon=False)
        case "Z":    return offset(moment, colon=True)
        case "X":    return str(int(moment.timestamp()))
        case "x":    return str(int(moment.timestamp() * 1000))
        case "Q":    return str((moment.month - 1) // 3 + 1)
        case "W":    return f"{moment.isocalendar().week:02d}"
        case "E":    return str(moment.isoweekday())
        case _:      return token

class Formatter:

    def format ( self, moment: datetime, pattern: str ) -> str:

        def swap ( found: re.Match[str] ) -> str:

            literal = found.group(1)

            return literal if literal is not None else piece(moment, found.group(0))

        return TOKEN.sub(swap, pattern)

    def relative ( self, seconds: float, short: bool = False ) -> str:

        distance = abs(seconds)

        if distance < JUST: return "just now"

        for size, unit in STEPS:

            if distance >= size:

                count = int(distance // size)
                label = f"{count}{unit[0]}" if short else f"{count} {unit}{'' if count == 1 else 's'}"

                return f"{label} ago" if seconds < 0 else f"in {label}"

        return "just now"

    def span ( self, seconds: float, short: bool = False ) -> str:

        left  = int(abs(seconds))
        parts: list[str] = []

        for size, unit in STEPS:

            if left < size or unit in ("week", "month"): continue

            count, left = divmod(left, size)

            parts.append(f"{count}{unit[0]}" if short else f"{count} {unit}{'' if count == 1 else 's'}")

        return " ".join(parts) if parts else ("0s" if short else "0 seconds")
