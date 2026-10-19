from collections.abc import Callable
from typing import Any, Self

from core.error import Code, Fault
from .checked import BOOK, SHIFTS, Checked

class Rule(Checked):

    __slots__ = ()

    def add ( self, name: str, *args: object ) -> Rule:

        step = f"{name}:{','.join(str(arg) for arg in args)}" if args else name

        return Rule((*self._steps, step), self._shifts, self._custom)

    def shift ( self, name: str ) -> Rule:

        if name not in SHIFTS: raise Fault(Code.INTERNAL, reason=f"validate.shift.{name}")

        return Rule(self._steps, (*self._shifts, name), self._custom)

    def where ( self, test: Callable[[Any], bool], message: str = "Invalid value" ) -> Rule:

        return Rule(self._steps, self._shifts, (*self._custom, (test, message)))

    def required ( self ) -> Rule:

        return self.add("required")

    def nullable ( self ) -> Rule:

        return self.add("nullable")

    def sometimes ( self ) -> Rule:

        return self.add("sometimes")

    def bail ( self ) -> Rule:

        return self.add("bail")

    def string ( self ) -> Rule:

        return self.add("string")

    def integer ( self ) -> Rule:

        return self.add("integer")

    def numeric ( self ) -> Rule:

        return self.add("numeric")

    def boolean ( self ) -> Rule:

        return self.add("boolean")

    def array ( self ) -> Rule:

        return self.add("array")

    def email ( self ) -> Rule:

        return self.add("email")

    def url ( self ) -> Rule:

        return self.add("url")

    def uuid ( self ) -> Rule:

        return self.add("uuid")

    def ip ( self ) -> Rule:

        return self.add("ip")

    def date ( self ) -> Rule:

        return self.add("date")

    def alpha ( self ) -> Rule:

        return self.add("alpha")

    def alpha_num ( self ) -> Rule:

        return self.add("alpha_num")

    def alpha_dash ( self ) -> Rule:

        return self.add("alpha_dash")

    def min ( self, size: float ) -> Rule:

        return self.add("min", size)

    def max ( self, size: float ) -> Rule:

        return self.add("max", size)

    def between ( self, low: float, high: float ) -> Rule:

        return self.add("between", low, high)

    def size ( self, exact: float ) -> Rule:

        return self.add("size", exact)

    def one_of ( self, *choices: object ) -> Rule:

        return self.add("in", *choices)

    def none_of ( self, *choices: object ) -> Rule:

        return self.add("not_in", *choices)

    def regex ( self, pattern: str ) -> Rule:

        return self.add("regex", pattern)

    def starts_with ( self, *prefixes: str ) -> Rule:

        return self.add("starts_with", *prefixes)

    def ends_with ( self, *suffixes: str ) -> Rule:

        return self.add("ends_with", *suffixes)

    def trim ( self ) -> Rule:

        return self.shift("trim")

    def lower ( self ) -> Rule:

        return self.shift("lower")

    def upper ( self ) -> Rule:

        return self.shift("upper")

    def squish ( self ) -> Rule:

        return self.shift("squish")

    def latin_digits ( self ) -> Rule:

        return self.shift("digits")

class Rules:

    def __call__ ( self ) -> Rule:

        return Rule()

    def text ( self, low: int = 1, high: int = 255 ) -> Rule:

        return Rule().string().trim().between(low, high)

    def number ( self, low: float | None = None, high: float | None = None ) -> Rule:

        built = Rule().numeric()

        if low is not None: built = built.min(low)
        if high is not None: built = built.max(high)

        return built

    def parse ( self, spec: str ) -> Rule:

        return Rule(tuple(piece for piece in spec.split("|") if piece))

    def extend ( self, name: str, check: Any ) -> Self:

        BOOK.extend(name, check)

        return self
