from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Self, override

from core.error import Code, Fault

ZERO  = frozenset({
    "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND", "VUV", "XAF", "XOF",
    "XPF",
})
THREE = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
CODE  = 3

def exponent ( currency: str ) -> int:

    if currency in ZERO: return 0

    return CODE if currency in THREE else 2

def amount_of ( value: object ) -> Decimal:

    try: return value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as error: raise Fault(Code.BAD_REQUEST, reason="money.amount") from error

@dataclass(frozen=True, slots=True)
class Money:

    amount   : Decimal
    currency : str

    @classmethod
    def of ( cls, value: object, currency: str ) -> Self:

        code = currency.strip().upper()

        if len(code) != CODE or not code.isalpha(): raise Fault(Code.BAD_REQUEST, reason="money.currency")

        step = Decimal(1).scaleb(-exponent(code))

        return cls(amount_of(value).quantize(step, rounding=ROUND_HALF_UP), code)

    @classmethod
    def minor_of ( cls, units: int, currency: str ) -> Self:

        code = currency.strip().upper()

        return cls.of(Decimal(units).scaleb(-exponent(code)), code)

    @classmethod
    def zero ( cls, currency: str ) -> Self:

        return cls.of(0, currency)

    @classmethod
    def total ( cls, items: Iterable[Money], currency: str ) -> Money:

        result: Money = cls.zero(currency)

        for item in items: result = result.add(item)

        return result

    def minor ( self ) -> int:

        return int(self.amount.scaleb(exponent(self.currency)))

    def same ( self, other: Money ) -> None:

        if other.currency != self.currency: raise Fault(Code.BAD_REQUEST, reason="money.currency_mismatch")

    def add ( self, other: Money ) -> Money:

        self.same(other)

        return Money.of(self.amount + other.amount, self.currency)

    def sub ( self, other: Money ) -> Money:

        self.same(other)

        return Money.of(self.amount - other.amount, self.currency)

    def times ( self, factor: object ) -> Money:

        return Money.of(self.amount * amount_of(factor), self.currency)

    def percent ( self, rate: object ) -> Money:

        return Money.of(self.amount * amount_of(rate) / 100, self.currency)

    def negate ( self ) -> Money:

        return Money.of(-self.amount, self.currency)

    def absolute ( self ) -> Money:

        return Money.of(abs(self.amount), self.currency)

    def allocate ( self, *ratios: int ) -> list[Money]:

        if not ratios or any(ratio < 0 for ratio in ratios) or sum(ratios) == 0:
            raise Fault(Code.BAD_REQUEST, reason="money.ratios")

        units  = self.minor()
        whole  = sum(ratios)
        shares = [units * ratio // whole for ratio in ratios]
        rest   = units - sum(shares)

        for index in range(abs(rest)): shares[index % len(shares)] += 1 if rest > 0 else -1

        return [Money.minor_of(share, self.currency) for share in shares]

    def split ( self, parts: int ) -> list[Money]:

        return self.allocate(*([1] * parts))

    def is_zero ( self ) -> bool:

        return self.amount == 0

    def positive ( self ) -> bool:

        return self.amount > 0

    def negative ( self ) -> bool:

        return self.amount < 0

    def format ( self, separator: str = "," ) -> str:

        places = exponent(self.currency)
        text   = f"{abs(self.amount):,.{places}f}".replace(",", separator)

        return f"{'-' if self.amount < 0 else ''}{text} {self.currency}"

    def dump ( self ) -> dict[str, Any]:

        return { "amount": str(self.amount), "currency": self.currency, "minor": self.minor() }

    def __add__ ( self, other: Money ) -> Money:

        return self.add(other)

    def __sub__ ( self, other: Money ) -> Money:

        return self.sub(other)

    def __lt__ ( self, other: Money ) -> bool:

        self.same(other)

        return self.amount < other.amount

    def __le__ ( self, other: Money ) -> bool:

        self.same(other)

        return self.amount <= other.amount

    @override
    def __str__ ( self ) -> str:

        return self.format()
