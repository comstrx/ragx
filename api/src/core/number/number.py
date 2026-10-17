from decimal import ROUND_HALF_UP, Decimal

THOUSAND = 1000

class Number:

    def clamp ( self, value: float, low: float, high: float ) -> float:
        return max(low, min(value, high))

    def between ( self, value: float, low: float, high: float ) -> bool:
        return low <= value <= high

    def ratio ( self, part: float, total: float, default: float = 0.0 ) -> float:
        return part / total if total else default

    def percent ( self, part: float, total: float, digits: int = 2 ) -> float:
        return self.round(self.ratio(part, total) * 100, digits)

    def round ( self, value: float, digits: int = 2 ) -> float:

        places = Decimal(1).scaleb(-digits)

        return float(Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP))

    def human ( self, value: float, digits: int = 1 ) -> str:

        units  = ("", "K", "M", "B", "T")
        size   = abs(value)
        index  = 0

        while size >= THOUSAND and index < len(units) - 1:

            size  /= THOUSAND
            index += 1

        sign = "-" if value < 0 else ""

        return f"{sign}{self.round(size, digits):g}{units[index]}"

    def pages ( self, total: int, limit: int ) -> int:
        return max(-(-max(total, 0) // max(limit, 1)), 1)
