from decimal import ROUND_HALF_UP, Decimal

from engine.error import Code, Fault
from .math import Math
from .money import Money
from .words import Words

THOUSAND = 1000
KILO     = 1024
UNITS    = ("", "K", "M", "B", "T")
SIZES    = ("B", "KB", "MB", "GB", "TB", "PB")
SPECIAL  = (11, 12, 13)
SUFFIXES = { 1: "st", 2: "nd", 3: "rd" }
ROMAN    = 4000

class Format:

    def human ( self, value: float, digits: int = 1 ) -> str:

        size  = abs(value)
        index = 0

        while size >= THOUSAND and index < len(UNITS) - 1:

            size  /= THOUSAND
            index += 1

        sign = "-" if value < 0 else ""

        return f"{sign}{self.rounded(size, digits):g}{UNITS[index]}"

    def bytes ( self, value: float, digits: int = 1, binary: bool = True ) -> str:

        base  = KILO if binary else THOUSAND
        size  = float(abs(value))
        index = 0

        while size >= base and index < len(SIZES) - 1:

            size  /= base
            index += 1

        sign = "-" if value < 0 else ""

        return f"{sign}{self.rounded(size, digits):g} {SIZES[index]}"

    def ordinal ( self, value: int ) -> str:

        suffix = "th" if value % 100 in SPECIAL else SUFFIXES.get(value % 10, "th")

        return f"{value}{suffix}"

    def thousands ( self, value: float, digits: int = 0, separator: str = "," ) -> str:

        text = f"{self.rounded(value, digits):,.{digits}f}"

        return text.replace(",", separator) if separator != "," else text

    def currency ( self, value: float, code: str = "USD", digits: int = 2 ) -> str:

        return f"{self.thousands(value, digits)} {code}"

    def pad ( self, value: int, width: int = 2 ) -> str:

        return f"{value:0{width}d}"

    def percentage ( self, value: float, digits: int = 1 ) -> str:

        return f"{self.rounded(value, digits):g}%"

    def compact ( self, value: float ) -> str:

        text = f"{value:.10f}".rstrip("0").rstrip(".")

        return text or "0"

    def roman ( self, value: int ) -> str:

        if not 0 < value < ROMAN: raise Fault(Code.BAD_REQUEST, reason="number.roman")

        numerals = (
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        )
        out = ""

        for amount, numeral in numerals:

            count, value = divmod(value, amount)
            out += numeral * count

        return out

    def rounded ( self, value: float, digits: int ) -> float:

        places = Decimal(1).scaleb(-digits)

        return float(Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP))

class Number(Math, Format, Words):

    def decimal ( self, value: object, places: int = 2 ) -> Decimal:

        number = Decimal(str(value)) if isinstance(value, int | float) else Decimal(str(value or 0))

        return number.quantize(Decimal(1).scaleb(-places))

    def money ( self, value: object, currency: str = "USD" ) -> Money:

        return Money.of(value, currency)

    def minor ( self, units: int, currency: str = "USD" ) -> Money:

        return Money.minor_of(units, currency)

    def is_number ( self, value: object ) -> bool:

        return isinstance(value, int | float | Decimal) and not isinstance(value, bool)
