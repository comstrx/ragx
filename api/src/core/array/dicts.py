from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from typing import Any, TypedDict

MISSING = object()

class Dicts:

    def merge ( self, base: Mapping[str, Any], *layers: Mapping[str, Any], deep: bool = True ) -> dict[str, Any]:

        merged: dict[str, Any] = dict(base)

        for layer in layers:

            for key, item in layer.items():

                known = merged.get(key)

                if deep and isinstance(known, Mapping) and isinstance(item, Mapping):
                    merged[key] = self.merge(known, item)
                else: merged[key] = item

        return merged

    def pick ( self, data: Mapping[str, Any], *keys: str ) -> dict[str, Any]:

        return { key: data[key] for key in keys if key in data }

    def omit ( self, data: Mapping[str, Any], *keys: str ) -> dict[str, Any]:

        dropped = set(keys)

        return { key: item for key, item in data.items() if key not in dropped }

    def only ( self, data: Mapping[str, Any], keys: Iterable[str] ) -> dict[str, Any]:

        return self.pick(data, *keys)

    def except_ ( self, data: Mapping[str, Any], keys: Iterable[str] ) -> dict[str, Any]:

        return self.omit(data, *keys)

    def get ( self, data: Mapping[str, Any], path: str, default: Any = None ) -> Any:

        current: Any = data

        for part in path.split("."):

            if isinstance(current, Mapping) and part in current: current = current[part]
            elif isinstance(current, list) and part.lstrip("-").isdigit() and -len(current) <= int(part) < len(current):
                current = current[int(part)]
            else: return default

        return current

    def has ( self, data: Mapping[str, Any], path: str ) -> bool:

        return self.get(data, path, MISSING) is not MISSING

    def put ( self, data: dict[str, Any], path: str, value: object ) -> dict[str, Any]:

        parts   = path.split(".")
        current = data

        for part in parts[:-1]:

            branch = current.get(part)

            if not isinstance(branch, dict): branch = current[part] = {}

            current = branch

        current[parts[-1]] = value

        return data

    def forget ( self, data: dict[str, Any], path: str ) -> bool:

        parts  = path.split(".")
        parent = self.get(data, ".".join(parts[:-1]), data) if len(parts) > 1 else data

        if isinstance(parent, dict) and parts[-1] in parent:

            del parent[parts[-1]]

            return True

        return False

    def defaults ( self, data: Mapping[str, Any], fallback: Mapping[str, Any] ) -> dict[str, Any]:

        return { **fallback, **data }

    def rename ( self, data: Mapping[str, Any], names: Mapping[str, str] ) -> dict[str, Any]:

        return { names.get(key, key): item for key, item in data.items() }

    def invert ( self, data: Mapping[Hashable, Hashable] ) -> dict[Hashable, Hashable]:

        return { item: key for key, item in data.items() }

    def map_values ( self, data: Mapping[str, Any], fn: Callable[[Any], Any] ) -> dict[str, Any]:

        return { key: fn(item) for key, item in data.items() }

    def map_keys ( self, data: Mapping[str, Any], fn: Callable[[str], str] ) -> dict[str, Any]:

        return { fn(key): item for key, item in data.items() }

    def filter_values ( self, data: Mapping[str, Any], test: Callable[[Any], bool] ) -> dict[str, Any]:

        return { key: item for key, item in data.items() if test(item) }

    def compact_dict ( self, data: Mapping[str, Any] ) -> dict[str, Any]:

        return { key: item for key, item in data.items() if item is not None }

    def sort_keys ( self, data: Mapping[str, Any] ) -> dict[str, Any]:

        return dict(sorted(data.items()))

    def walk ( self, data: Any, fn: Callable[[Any], Any] ) -> Any:

        if isinstance(data, Mapping): return { key: self.walk(item, fn) for key, item in data.items() }
        if isinstance(data, list): return [self.walk(item, fn) for item in data]

        return fn(data)

    def dot ( self, data: Mapping[str, Any], prefix: str = "" ) -> dict[str, Any]:

        flat: dict[str, Any] = {}

        for key, item in data.items():

            path = f"{prefix}.{key}" if prefix else str(key)

            if isinstance(item, Mapping) and item: flat.update(self.dot(item, path))
            else: flat[path] = item

        return flat

    def undot ( self, flat: Mapping[str, Any] ) -> dict[str, Any]:

        nested: dict[str, Any] = {}

        for path, item in flat.items(): self.put(nested, str(path), item)

        return nested

class Sets:

    def diff[T: Hashable] ( self, left: Iterable[T], right: Iterable[T] ) -> list[T]:

        gone = set(right)

        return [item for item in dict.fromkeys(left) if item not in gone]

    def intersect[T: Hashable] ( self, left: Iterable[T], right: Iterable[T] ) -> list[T]:

        kept = set(right)

        return [item for item in dict.fromkeys(left) if item in kept]

    def union[T: Hashable] ( self, *groups: Iterable[T] ) -> list[T]:

        return list(dict.fromkeys(item for group in groups for item in group))

    def symmetric[T: Hashable] ( self, left: Iterable[T], right: Iterable[T] ) -> list[T]:

        a = list(dict.fromkeys(left))
        b = list(dict.fromkeys(right))

        return [*self.diff(a, b), *self.diff(b, a)]

    def same[T: Hashable] ( self, left: Iterable[T], right: Iterable[T] ) -> bool:

        return set(left) == set(right)

    def contains_all[T: Hashable] ( self, items: Iterable[T], wanted: Iterable[T] ) -> bool:

        return set(wanted) <= set(items)

    def contains_any[T: Hashable] ( self, items: Iterable[T], wanted: Iterable[T] ) -> bool:

        return bool(set(wanted) & set(items))

    def added[T: Hashable] ( self, before: Iterable[T], after: Iterable[T] ) -> list[T]:

        return self.diff(after, before)

    def removed[T: Hashable] ( self, before: Iterable[T], after: Iterable[T] ) -> list[T]:

        return self.diff(before, after)

class Page(TypedDict):

    page  : int
    limit : int
    total : int
    pages : int

class Pager:

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

    def has_next ( self, meta: Page ) -> bool:

        return meta["page"] < meta["pages"]

    def has_previous ( self, meta: Page ) -> bool:

        return meta["page"] > 1

    def bounds ( self, meta: Page ) -> tuple[int, int]:

        if meta["total"] == 0: return 0, 0

        start = (meta["page"] - 1) * meta["limit"] + 1

        return start, min(start + meta["limit"] - 1, meta["total"])
