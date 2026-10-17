from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from typing import TypedDict

from core.string import string

class Page(TypedDict):

    page  : int
    limit : int
    total : int
    pages : int

class Array:

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

    def flatten[T] ( self, items: Iterable[Iterable[T]] ) -> list[T]:
        return [item for group in items for item in group]

    def compact[T] ( self, items: Iterable[T | None] ) -> list[T]:
        return [item for item in items if item is not None]

    def pluck ( self, rows: Iterable[Mapping[str, object]], field: str ) -> list[object]:
        return [row[field] for row in rows if field in row]

    def group[T, K: Hashable] ( self, items: Iterable[T], key: Callable[[T], K] ) -> dict[K, list[T]]:

        groups: dict[K, list[T]] = {}

        for item in items: groups.setdefault(key(item), []).append(item)

        return groups

    def index[T, K: Hashable] ( self, items: Iterable[T], key: Callable[[T], K] ) -> dict[K, T]:
        return {key(item): item for item in items}

    def partition[T] ( self, items: Iterable[T], test: Callable[[T], bool] ) -> tuple[list[T], list[T]]:

        passed: list[T] = []
        failed: list[T] = []

        for item in items: (passed if test(item) else failed).append(item)

        return passed, failed

    def first[T] ( self, items: Iterable[T], default: T | None = None ) -> T | None:
        return next(iter(items), default)

    def last[T] ( self, items: Sequence[T], default: T | None = None ) -> T | None:
        return items[-1] if items else default

    def windows[T] ( self, items: Sequence[T], size: int ) -> Iterator[Sequence[T]]:

        if size <= 0: raise ValueError(size)

        for i in range(max(len(items) - size + 1, 0)): yield items[i : i + size]

    def page ( self, total: int, page: int = 1, limit: int = 20 ) -> Page:

        limit = max(limit, 1)
        pages = max(-(-total // limit), 1)

        return { "page": min(max(page, 1), pages), "limit": limit, "total": total, "pages": pages }

    def slice[T] ( self, items: Sequence[T], page: int = 1, limit: int = 20 ) -> tuple[list[T], Page]:

        meta  = self.page(len(items), page, limit)
        start = (meta["page"] - 1) * meta["limit"]

        return list(items[start : start + meta["limit"]]), meta

    def offset ( self, page: int = 1, limit: int = 20 ) -> int:
        return (max(page, 1) - 1) * max(limit, 1)

    def to_base64 ( self, items: Iterable[int], url: bool = False ) -> str:
        return string.to_base64(bytes(items), url)

    def from_base64 ( self, text: str, url: bool = False ) -> list[int]:
        return list(string.from_base64(text, url))
