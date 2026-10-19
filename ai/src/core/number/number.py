from decimal import Decimal

from .format import Format
from .math import Math
from .money import Money
from .words import Words

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
