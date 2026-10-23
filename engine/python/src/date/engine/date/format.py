from datetime import UTC, datetime, tzinfo

from engine.error import Code, Fault
from .human import Human
import re

TOKEN   = re.compile(
    r"\[([^\]]*)\]|YYYY|YY|MMMM|MMM|MM|M|DDDD|DD|Do|D|dddd|ddd|d|HH|H|hh|h|mm|m|ss|s|SSS|A|a|ZZ|Z|X|x|Q|W|E",
)
SPECIAL = (11, 12, 13)
SUFFIX  = { 1: "st", 2: "nd", 3: "rd" }
MINUTE  = 60
NOON    = 12
STRP    = {
    "YYYY": "%Y", "YY": "%y", "MMMM": "%B", "MMM": "%b", "MM": "%m", "M": "%m", "DD": "%d", "D": "%d", "dddd": "%A",
    "ddd": "%a", "HH": "%H", "H": "%H", "hh": "%I", "h": "%I", "mm": "%M", "m": "%M", "ss": "%S", "s": "%S",
    "SSS": "%f", "A": "%p", "a": "%p", "ZZ": "%z", "Z": "%z",
}
human   = Human()

def ordinal ( value: int ) -> str:

    return f"{value}{'th' if value % 100 in SPECIAL else SUFFIX.get(value % 10, 'th')}"

def offset ( moment: datetime, colon: bool ) -> str:

    delta = moment.utcoffset()

    if delta is None: return "+00:00" if colon else "+0000"

    total = int(delta.total_seconds())
    sign  = "-" if total < 0 else "+"
    hours, minutes = divmod(abs(total) // MINUTE, MINUTE)

    return f"{sign}{hours:02d}{':' if colon else ''}{minutes:02d}"

def meridiem ( moment: datetime, locale: str ) -> str:

    if locale == "ar": return "ص" if moment.hour < NOON else "م"

    return "AM" if moment.hour < NOON else "PM"

def piece ( moment: datetime, token: str, locale: str = "en" ) -> str:

    match token:
        case "YYYY": return f"{moment.year:04d}"
        case "YY":   return f"{moment.year % 100:02d}"
        case "MMMM": return human.month(moment, locale)
        case "MMM":  return human.month(moment, locale, short=True)
        case "MM":   return f"{moment.month:02d}"
        case "M":    return str(moment.month)
        case "DDDD": return f"{moment.timetuple().tm_yday:03d}"
        case "DD":   return f"{moment.day:02d}"
        case "Do":   return ordinal(moment.day)
        case "D":    return str(moment.day)
        case "dddd": return human.day(moment, locale)
        case "ddd":  return human.day(moment, locale, short=True)
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
        case "A":    return meridiem(moment, locale)
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

    def format ( self, moment: datetime, pattern: str, locale: str = "en" ) -> str:

        def swap ( found: re.Match[str] ) -> str:

            literal = found.group(1)

            return literal if literal is not None else piece(moment, found.group(0), locale)

        return TOKEN.sub(swap, pattern)

    def strptime ( self, pattern: str ) -> str:

        def swap ( found: re.Match[str] ) -> str:

            literal = found.group(1)

            if literal is not None: return literal.replace("%", "%%")

            token = found.group(0)

            if token not in STRP: raise Fault(Code.BAD_REQUEST, reason="date.token")

            return STRP[token]

        return TOKEN.sub(swap, pattern)

    def read ( self, text: str, pattern: str, zone: tzinfo = UTC ) -> datetime:

        try: parsed = datetime.strptime(text.strip(), self.strptime(pattern))
        except ValueError as error: raise Fault(Code.BAD_REQUEST, reason="date.format") from error

        return parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)

    def relative ( self, seconds: float, short: bool = False, locale: str = "en", absolute: bool = False ) -> str:

        return human.relative(seconds, short, locale, absolute)

    def span ( self, seconds: float, short: bool = False, locale: str = "en", parts: int = 7 ) -> str:

        return human.span(seconds, short, locale, parts)
