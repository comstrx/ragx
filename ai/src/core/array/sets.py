from collections.abc import Hashable, Iterable

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
