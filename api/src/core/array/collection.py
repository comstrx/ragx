from collections.abc import Callable, Hashable, Iterable, Iterator
from typing import Any, Self, SupportsFloat, cast, override

from core.string import string
from .collect import Collect
from .dicts import Dicts, Page, Pager, Sets
from .query import Query, field

class Kit(Collect, Dicts, Sets, Pager, Query):

    pass

KIT = Kit()

class Collection[T]:

    __slots__ = ("_items",)

    def __init__ ( self, items: Iterable[T] = () ) -> None:

        self._items: list[T] = list(items)

    def all ( self ) -> list[T]:

        return list(self._items)

    def map[R] ( self, fn: Callable[[T], R] ) -> Collection[R]:

        return Collection(fn(item) for item in self._items)

    def filter ( self, test: Callable[[T], bool] | None = None ) -> Self:

        return type(self)(item for item in self._items if (test(item) if test else item))

    def reject ( self, test: Callable[[T], bool] ) -> Self:

        return type(self)(item for item in self._items if not test(item))

    def where ( self, name: str, *args: Any ) -> Self:

        return type(self)(KIT.where(self._items, name, *args))

    def where_in ( self, name: str, values: Iterable[Any] ) -> Self:

        return type(self)(KIT.where_in(self._items, name, values))

    def where_not_in ( self, name: str, values: Iterable[Any] ) -> Self:

        return type(self)(KIT.where_not_in(self._items, name, values))

    def pluck ( self, name: str ) -> Collection[Any]:

        return Collection(field(item, name) for item in self._items)

    def key_by ( self, name: str ) -> dict[Any, T]:

        return { field(item, name): item for item in self._items }

    def group_by[K: Hashable] ( self, key: Callable[[T], K] ) -> dict[K, list[T]]:

        return KIT.group(self._items, key)

    def count_by[K: Hashable] ( self, key: Callable[[T], K] ) -> dict[K, int]:

        return KIT.count_by(self._items, key)

    def sort_by ( self, key: Callable[[T], Any], reverse: bool = False ) -> Self:

        return type(self)(KIT.sort_by(self._items, key, reverse))

    def sort_by_desc ( self, key: Callable[[T], Any] ) -> Self:

        return self.sort_by(key, reverse=True)

    def unique ( self, key: Callable[[T], Hashable] | None = None ) -> Self:

        return type(self)(KIT.unique(self._items, key))

    def chunk ( self, size: int ) -> list[list[T]]:

        return KIT.chunk(self._items, size)

    def take ( self, count: int ) -> Self:

        return type(self)(KIT.take(self._items, count))

    def skip ( self, count: int ) -> Self:

        return type(self)(KIT.skip(self._items, count))

    def reverse ( self ) -> Self:

        return type(self)(reversed(self._items))

    def push ( self, *items: T ) -> Self:

        return type(self)([*self._items, *items])

    def prepend ( self, *items: T ) -> Self:

        return type(self)([*items, *self._items])

    def merge ( self, items: Iterable[T] ) -> Self:

        return type(self)([*self._items, *items])

    def flat_map[R] ( self, fn: Callable[[T], Iterable[R]] ) -> Collection[R]:

        return Collection(KIT.flat_map(self._items, fn))

    def partition ( self, test: Callable[[T], bool] ) -> tuple[Self, Self]:

        passed, failed = KIT.partition(self._items, test)

        return type(self)(passed), type(self)(failed)

    def first ( self, test: Callable[[T], bool] | None = None, default: T | None = None ) -> T | None:

        return KIT.find(self._items, test, default) if test else KIT.first(self._items, default)

    def last ( self, default: T | None = None ) -> T | None:

        return KIT.last(self._items, default)

    def sole ( self, test: Callable[[T], bool] | None = None ) -> T:

        return KIT.sole(self._items, test)

    def reduce[R] ( self, fold: Callable[[R, T], R], start: R ) -> R:

        return KIT.reduce(self._items, fold, start)

    def sum ( self, key: Callable[[T], float] | None = None ) -> float:

        if key is not None: return KIT.sum_by(self._items, key)

        return float(sum(float(cast("SupportsFloat", item)) for item in self._items))

    def avg ( self, key: Callable[[T], float] | None = None ) -> float:

        if not self._items: return 0.0

        return self.sum(key) / len(self._items)

    def min ( self, key: Callable[[T], Any] ) -> T | None:

        return KIT.min_by(self._items, key)

    def max ( self, key: Callable[[T], Any] ) -> T | None:

        return KIT.max_by(self._items, key)

    def every ( self, test: Callable[[T], bool] ) -> bool:

        return KIT.every(self._items, test)

    def some ( self, test: Callable[[T], bool] ) -> bool:

        return KIT.some(self._items, test)

    def contains ( self, item: object ) -> bool:

        return item in self._items

    def each ( self, fn: Callable[[T], object] ) -> Self:

        for item in self._items: fn(item)

        return self

    def pipe[R] ( self, fn: Callable[[Self], R] ) -> R:

        return fn(self)

    def tap ( self, look: Callable[[Self], object] ) -> Self:

        look(self)

        return self

    def when ( self, condition: object, step: Callable[[Self], Self] ) -> Self:

        return step(self) if condition else self

    def unless ( self, condition: object, step: Callable[[Self], Self] ) -> Self:

        return self if condition else step(self)

    def page ( self, page: int = 1, limit: int = 20 ) -> tuple[list[T], Page]:

        return KIT.slice(self._items, page, limit)

    def implode ( self, glue: str = ", ", final: str | None = None ) -> str:

        return KIT.implode(self._items, glue, final)

    def count ( self ) -> int:

        return len(self._items)

    def is_empty ( self ) -> bool:

        return not self._items

    def __len__ ( self ) -> int:

        return len(self._items)

    def __iter__ ( self ) -> Iterator[T]:

        return iter(self._items)

    def __getitem__ ( self, index: int ) -> T:

        return self._items[index]

    @override
    def __repr__ ( self ) -> str:

        return f"Collection({self._items!r})"

class Array(Kit):

    def of[T] ( self, items: Iterable[T] = () ) -> Collection[T]:

        return Collection(items)

    def to_base64 ( self, items: Iterable[int], url: bool = False ) -> str:

        return string.to_base64(bytes(items), url)

    def from_base64 ( self, text: str, url: bool = False ) -> list[int]:

        return list(string.from_base64(text, url))
