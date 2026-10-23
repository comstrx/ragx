from collections.abc import Callable, Container, Iterable, Mapping, Sized
from typing import Any, NoReturn, Self

import math, re

MISSING = object()

class Mismatch(AssertionError):

    def __init__ ( self, message: str ) -> None:

        super().__init__(message)

def mismatch ( message: str ) -> NoReturn:

    raise Mismatch(message)

def dig ( value: Any, path: str ) -> Any:

    current = value

    for part in path.split(".") if path else ():

        indexed = isinstance(current, list | tuple) and part.lstrip("-").isdigit()

        if isinstance(current, Mapping): current = current.get(part, MISSING)
        elif indexed and -len(current) <= int(part) < len(current): current = current[int(part)]
        else: current = getattr(current, part, MISSING)

        if current is MISSING: return MISSING

    return current

def lookup ( actual: Any, key: str ) -> Any:

    if isinstance(actual, Mapping): return actual[key] if key in actual else dig(actual, key)

    return getattr(actual, key, MISSING)

def differences ( expected: Mapping[str, Any], actual: Any, prefix: str = "" ) -> list[str]:

    found: list[str] = []

    for key, wanted in expected.items():

        here  = f"{prefix}{key}"
        value = lookup(actual, str(key))

        nested = isinstance(wanted, Mapping) and isinstance(value, Mapping)

        if value is MISSING: found.append(f"{here} is missing")
        elif nested: found.extend(differences(wanted, value, f"{here}."))
        elif value != wanted: found.append(f"{here}: expected {wanted!r}, got {value!r}")

    return found

class Expect:

    __slots__ = ("label", "value")

    def __init__ ( self, value: Any, label: str = "value" ) -> None:

        self.value = value
        self.label = label

    def fail ( self, message: str ) -> NoReturn:

        mismatch(f"{self.label}: {message}")

    def check ( self, passed: bool, message: str ) -> Self:

        if not passed: self.fail(message)

        return self

    def equals ( self, expected: object ) -> Self:

        return self.check(self.value == expected, f"expected {expected!r}, got {self.value!r}")

    def differs ( self, unexpected: object ) -> Self:

        return self.check(self.value != unexpected, f"expected anything but {unexpected!r}")

    def is_ ( self, expected: object ) -> Self:

        return self.check(self.value is expected, f"expected the very object {expected!r}, got {self.value!r}")

    def true ( self ) -> Self:

        return self.check(self.value is True, f"expected True, got {self.value!r}")

    def false ( self ) -> Self:

        return self.check(self.value is False, f"expected False, got {self.value!r}")

    def none ( self ) -> Self:

        return self.check(self.value is None, f"expected None, got {self.value!r}")

    def some ( self ) -> Self:

        return self.check(self.value is not None, "expected a value, got None")

    def truthy ( self ) -> Self:

        return self.check(bool(self.value), f"expected a truthy value, got {self.value!r}")

    def falsy ( self ) -> Self:

        return self.check(not self.value, f"expected a falsy value, got {self.value!r}")

    def instance_of ( self, *kinds: type ) -> Self:

        names = ", ".join(kind.__name__ for kind in kinds)

        return self.check(isinstance(self.value, kinds), f"expected {names}, got {type(self.value).__name__}")

    def contains ( self, *items: object ) -> Self:

        held = self.value if isinstance(self.value, Container) else ()
        lost = [item for item in items if item not in held]

        return self.check(not lost, f"expected to contain {lost!r} in {self.value!r}")

    def lacks ( self, *items: object ) -> Self:

        held  = self.value if isinstance(self.value, Container) else ()
        found = [item for item in items if item in held]

        return self.check(not found, f"expected not to contain {found!r} in {self.value!r}")

    def starts_with ( self, prefix: str ) -> Self:

        return self.check(str(self.value).startswith(prefix), f"expected to start with {prefix!r}, got {self.value!r}")

    def ends_with ( self, suffix: str ) -> Self:

        return self.check(str(self.value).endswith(suffix), f"expected to end with {suffix!r}, got {self.value!r}")

    def matches ( self, pattern: str ) -> Self:

        found = re.search(pattern, str(self.value)) is not None

        return self.check(found, f"expected to match {pattern!r}, got {self.value!r}")

    def length ( self, size: int ) -> Self:

        actual = len(self.value) if isinstance(self.value, Sized) else None

        return self.check(actual == size, f"expected length {size}, got {actual}")

    def empty ( self ) -> Self:

        return self.length(0)

    def filled ( self ) -> Self:

        return self.check(isinstance(self.value, Sized) and len(self.value) > 0, f"expected items, got {self.value!r}")

    def between ( self, low: Any, high: Any ) -> Self:

        return self.check(low <= self.value <= high, f"expected between {low} and {high}, got {self.value!r}")

    def above ( self, bound: Any ) -> Self:

        return self.check(self.value > bound, f"expected above {bound}, got {self.value!r}")

    def below ( self, bound: Any ) -> Self:

        return self.check(self.value < bound, f"expected below {bound}, got {self.value!r}")

    def near ( self, expected: float, tolerance: float = 1e-9 ) -> Self:

        close = math.isclose(float(self.value), expected, abs_tol=tolerance)

        return self.check(close, f"expected {expected}±{tolerance}, got {self.value!r}")

    def keys ( self, *names: str ) -> Self:

        held = self.value if isinstance(self.value, Mapping) else {}
        lost = [name for name in names if name not in held]

        return self.check(not lost, f"expected keys {lost!r} in {sorted(held)!r}")

    def subset ( self, expected: Mapping[str, Any] ) -> Self:

        found = differences(expected, self.value)

        return self.check(not found, "; ".join(found))

    def each ( self, predicate: Callable[[Any], bool], message: str = "an item failed" ) -> Self:

        items = self.value if isinstance(self.value, Iterable) else ()
        wrong = [item for item in items if not predicate(item)]

        return self.check(not wrong, f"{message}: {wrong!r}")

    def satisfies ( self, predicate: Callable[[Any], bool], message: str = "the predicate failed" ) -> Self:

        return self.check(predicate(self.value), f"{message} for {self.value!r}")

    def at ( self, path: str ) -> Expect:

        found = dig(self.value, path)

        if found is MISSING: self.fail(f"{path} is missing")

        return Expect(found, f"{self.label}.{path}")
