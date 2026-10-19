from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from typing import Any

from core.error import Code, Fault

type Row = Mapping[str, Any]
type Test[T] = Callable[[T], bool]
type Key[T] = Callable[[T], Any]

PAIR = 2

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "="  : lambda left, right: bool(left == right),
    "!=" : lambda left, right: bool(left != right),
    ">"  : lambda left, right: bool(left > right),
    ">=" : lambda left, right: bool(left >= right),
    "<"  : lambda left, right: bool(left < right),
    "<=" : lambda left, right: bool(left <= right),
    "in" : lambda left, right: left in right,
}

def field ( item: Any, name: str ) -> Any:

    return item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)

class Query:

    def where ( self, items: Iterable[Any], name: str, *args: Any ) -> list[Any]:

        operator, value = ("=", args[0]) if len(args) == 1 else (str(args[0]), args[1])
        compare         = OPERATORS.get(operator)

        if compare is None: raise Fault(Code.BAD_REQUEST, reason=f"array.operator.{operator}")

        return [item for item in items if compare(field(item, name), value)]

    def where_in ( self, items: Iterable[Any], name: str, values: Iterable[Any] ) -> list[Any]:

        wanted = set(values)

        return [item for item in items if field(item, name) in wanted]

    def where_not_in ( self, items: Iterable[Any], name: str, values: Iterable[Any] ) -> list[Any]:

        unwanted = set(values)

        return [item for item in items if field(item, name) not in unwanted]

    def where_not_none ( self, items: Iterable[Any], name: str ) -> list[Any]:

        return [item for item in items if field(item, name) is not None]

    def first_where ( self, items: Iterable[Any], name: str, value: Any, default: Any = None ) -> Any:

        return next((item for item in items if field(item, name) == value), default)

    def sole[T] ( self, items: Iterable[T], test: Test[T] | None = None ) -> T:

        found = [item for item in items if test is None or test(item)]

        if len(found) != 1: raise Fault(Code.NOT_FOUND if not found else Code.CONFLICT, reason="array.sole")

        return found[0]

    def nth[T] ( self, items: Sequence[T], step: int, offset: int = 0 ) -> list[T]:

        if step <= 0: raise Fault(Code.BAD_REQUEST, reason="array.step")

        return list(items[offset::step])

    def min_by[T] ( self, items: Iterable[T], key: Key[T], default: T | None = None ) -> T | None:

        listed = list(items)

        return min(listed, key=key) if listed else default

    def max_by[T] ( self, items: Iterable[T], key: Key[T], default: T | None = None ) -> T | None:

        listed = list(items)

        return max(listed, key=key) if listed else default

    def avg_by[T] ( self, items: Iterable[T], key: Callable[[T], float], default: float = 0.0 ) -> float:

        values = [key(item) for item in items]

        return sum(values) / len(values) if values else default

    def duplicates[T] ( self, items: Iterable[T], key: Callable[[T], Hashable] | None = None ) -> list[T]:

        seen: set[Hashable] = set()
        twice: list[T]      = []

        for item in items:

            mark = key(item) if key else item

            if mark in seen and item not in twice: twice.append(item)

            seen.add(mark)

        return twice

    def take_while[T] ( self, items: Iterable[T], test: Test[T] ) -> list[T]:

        kept: list[T] = []

        for item in items:

            if not test(item): break

            kept.append(item)

        return kept

    def skip_while[T] ( self, items: Iterable[T], test: Test[T] ) -> list[T]:

        listed  = list(items)
        skipped = 0

        for item in listed:

            if not test(item): break

            skipped += 1

        return listed[skipped:]

    def split[T] ( self, items: Sequence[T], parts: int ) -> list[list[T]]:

        if parts <= 0: raise Fault(Code.BAD_REQUEST, reason="array.parts")

        size, extra = divmod(len(items), parts)
        groups: list[list[T]] = []
        start = 0

        for index in range(parts):

            end = start + size + (1 if index < extra else 0)

            groups.append(list(items[start:end]))

            start = end

        return groups

    def transpose[T] ( self, rows: Sequence[Sequence[T]] ) -> list[list[T]]:

        return [list(column) for column in zip(*rows, strict=True)] if rows else []

    def flat_map[T, R] ( self, items: Iterable[T], fn: Callable[[T], Iterable[R]] ) -> list[R]:

        return [out for item in items for out in fn(item)]

    def combine[K, V] ( self, keys: Sequence[K], values: Sequence[V] ) -> dict[K, V]:

        return dict(zip(keys, values, strict=True))

    def divide[T] ( self, items: Iterable[T], test: Test[T] ) -> tuple[list[T], list[T]]:

        yes: list[T] = []
        no: list[T]  = []

        for item in items: (yes if test(item) else no).append(item)

        return yes, no

    def pad[T] ( self, items: Sequence[T], size: int, value: T ) -> list[T]:

        listed = list(items)

        if size >= 0: return listed + [value] * max(size - len(listed), 0)

        return [value] * max(-size - len(listed), 0) + listed

    def prepend[T] ( self, items: Iterable[T], *values: T ) -> list[T]:

        return [*values, *items]

    def collapse ( self, groups: Iterable[Iterable[Any]] ) -> list[Any]:

        return [item for group in groups for item in group]

    def sort_by_desc[T] ( self, items: Iterable[T], key: Key[T] ) -> list[T]:

        return sorted(items, key=key, reverse=True)

    def tally ( self, items: Iterable[Hashable] ) -> dict[Hashable, int]:

        counts: dict[Hashable, int] = {}

        for item in items: counts[item] = counts.get(item, 0) + 1

        return counts

    def mode[T: Hashable] ( self, items: Iterable[T] ) -> T | None:

        counts: dict[T, int] = {}

        for item in items: counts[item] = counts.get(item, 0) + 1

        return max(counts, key=lambda item: counts[item]) if counts else None

    def key_by ( self, items: Iterable[Any], name: str ) -> dict[Any, Any]:

        return { field(item, name): item for item in items }

    def pluck_many ( self, items: Iterable[Any], *names: str ) -> list[dict[str, Any]]:

        return [{ name: field(item, name) for name in names } for item in items]

    def implode ( self, items: Iterable[Any], glue: str = ", ", final: str | None = None ) -> str:

        words = [str(item) for item in items]

        if final is None or len(words) < PAIR: return glue.join(words)

        return f"{glue.join(words[:-1])}{final}{words[-1]}"
