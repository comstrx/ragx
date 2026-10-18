from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from typing import Any

class Collect:

    def chunk[T] ( self, items: Sequence[T], size: int ) -> list[list[T]]:

        if size <= 0: raise ValueError(size)

        return [list(items[i : i + size]) for i in range(0, len(items), size)]

    def unique[T] ( self, items: Iterable[T], key: Callable[[T], Hashable] | None = None ) -> list[T]:

        seen: set[Hashable] = set()
        kept: list[T]       = []

        for item in items:

            mark = key(item) if key else item

            if mark in seen: continue

            seen.add(mark)
            kept.append(item)

        return kept

    def flatten ( self, items: Iterable[Any], deep: bool = False ) -> list[Any]:

        flat: list[Any] = []

        for group in items:

            if isinstance(group, Iterable) and not isinstance(group, str | bytes | Mapping):
                flat.extend(self.flatten(group, deep=True) if deep else group)
            else: flat.append(group)

        return flat

    def compact[T] ( self, items: Iterable[T | None] ) -> list[T]:
        return [item for item in items if item is not None]

    def wrap ( self, value: object ) -> list[Any]:

        if value is None: return []
        if isinstance(value, list): return value
        if isinstance(value, tuple | set | frozenset): return list(value)

        return [value]

    def pluck ( self, rows: Iterable[Mapping[str, object]], field: str ) -> list[object]:
        return [row[field] for row in rows if field in row]

    def group[T, K: Hashable] ( self, items: Iterable[T], key: Callable[[T], K] ) -> dict[K, list[T]]:

        groups: dict[K, list[T]] = {}

        for item in items: groups.setdefault(key(item), []).append(item)

        return groups

    def index[T, K: Hashable] ( self, items: Iterable[T], key: Callable[[T], K] ) -> dict[K, T]:
        return {key(item): item for item in items}

    def count_by[T, K: Hashable] ( self, items: Iterable[T], key: Callable[[T], K] ) -> dict[K, int]:

        counts: dict[K, int] = {}

        for item in items: counts[key(item)] = counts.get(key(item), 0) + 1

        return counts

    def sum_by[T] ( self, items: Iterable[T], key: Callable[[T], float] ) -> float:
        return sum(key(item) for item in items)

    def sort_by[T] ( self, items: Iterable[T], key: Callable[[T], Any], reverse: bool = False ) -> list[T]:
        return sorted(items, key=key, reverse=reverse)

    def partition[T] ( self, items: Iterable[T], test: Callable[[T], bool] ) -> tuple[list[T], list[T]]:

        passed: list[T] = []
        failed: list[T] = []

        for item in items: (passed if test(item) else failed).append(item)

        return passed, failed

    def first[T] ( self, items: Iterable[T], default: T | None = None ) -> T | None:
        return next(iter(items), default)

    def last[T] ( self, items: Sequence[T], default: T | None = None ) -> T | None:
        return items[-1] if items else default

    def find[T] ( self, items: Iterable[T], test: Callable[[T], bool], default: T | None = None ) -> T | None:
        return next((item for item in items if test(item)), default)

    def take[T] ( self, items: Sequence[T], count: int ) -> list[T]:
        return list(items[:count]) if count >= 0 else list(items[count:])

    def skip[T] ( self, items: Sequence[T], count: int ) -> list[T]:
        return list(items[count:])

    def windows[T] ( self, items: Sequence[T], size: int ) -> Iterator[Sequence[T]]:

        if size <= 0: raise ValueError(size)

        for i in range(max(len(items) - size + 1, 0)): yield items[i : i + size]

    def pairs[T] ( self, items: Sequence[T] ) -> list[tuple[T, T]]:
        return [(items[i], items[i + 1]) for i in range(len(items) - 1)]

    def cross[T, U] ( self, left: Iterable[T], right: Iterable[U] ) -> list[tuple[T, U]]:

        rights = list(right)

        return [(a, b) for a in left for b in rights]

    def zip_dicts ( self, keys: Sequence[str], rows: Iterable[Sequence[object]] ) -> list[dict[str, object]]:
        return [dict(zip(keys, row, strict=False)) for row in rows]

    def every[T] ( self, items: Iterable[T], test: Callable[[T], bool] ) -> bool:
        return all(test(item) for item in items)

    def some[T] ( self, items: Iterable[T], test: Callable[[T], bool] ) -> bool:
        return any(test(item) for item in items)

    def times[T] ( self, count: int, make: Callable[[int], T] ) -> list[T]:
        return [make(index) for index in range(max(count, 0))]

    def interleave[T] ( self, *groups: Sequence[T] ) -> list[T]:

        longest = max((len(group) for group in groups), default=0)

        return [group[index] for index in range(longest) for group in groups if index < len(group)]

    def reduce[T, R] ( self, items: Iterable[T], fold: Callable[[R, T], R], start: R ) -> R:

        total = start

        for item in items: total = fold(total, item)

        return total

    def rotate[T] ( self, items: Sequence[T], steps: int ) -> list[T]:

        if not items: return []

        shift = steps % len(items)

        return [*items[shift:], *items[:shift]]
