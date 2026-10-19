from collections.abc import Iterable, Sequence
from typing import Self

from core.error import Code, Fault
import sqlalchemy as sa
from .model import Model
from .scope import BUILDERS, ORDERS, PAIR, Condition, Filter, Scope, Values, clause, condition, plain

class Filters[M: Model](Scope[M]):

    def where ( self, column: str, *args: object ) -> Self:

        if len(args) == 1: return self.where_raw(clause(column, "=", args[0]))
        if len(args) == PAIR and isinstance(args[0], str): return self.where_raw(clause(column, args[0], args[1]))

        raise Fault(Code.INTERNAL, reason=f"database.where.{column}")

    def where_not ( self, column: str, value: object ) -> Self:

        return self.where(column, "!=", value)

    def where_in ( self, column: str, values: Iterable[object] ) -> Self:

        return self.where(column, "in", list(values))

    def where_not_in ( self, column: str, values: Iterable[object] ) -> Self:

        return self.where(column, "not in", list(values))

    def where_null ( self, column: str ) -> Self:

        return self.where(column, None)

    def where_not_null ( self, column: str ) -> Self:

        return self.where(column, "!=", None)

    def where_like ( self, column: str, pattern: str, insensitive: bool = True ) -> Self:

        return self.where(column, "ilike" if insensitive else "like", pattern)

    def where_not_like ( self, column: str, pattern: str, insensitive: bool = True ) -> Self:

        return self.where(column, "not ilike" if insensitive else "not like", pattern)

    def where_between ( self, column: str, low: object, high: object ) -> Self:

        return self.where(column, ">=", low).where(column, "<=", high)

    def where_not_between ( self, column: str, low: object, high: object ) -> Self:

        return self.where_raw(lambda table: sa.not_(table.c[column].between(plain(low), plain(high))))

    def where_date ( self, column: str, day: object ) -> Self:

        return self.where_raw(lambda table: sa.cast(table.c[column], sa.Date) == day)

    def where_all ( self, **equals: object ) -> Self:

        scoped = self

        for column, value in equals.items(): scoped = scoped.where(column, value)

        return scoped

    def where_either ( self, *conditions: Condition ) -> Self:

        built = [condition(item) for item in conditions]

        return self.where_raw(lambda table: sa.or_(*(build(table) for build in built)))

    def where_column ( self, left: str, operator: str, right: str ) -> Self:

        builder = BUILDERS.get(operator.lower())

        if builder is None: raise Fault(Code.INTERNAL, reason=f"database.operator.{operator}")

        return self.where_raw(lambda table: builder(table.c[left], table.c[right]))

    def where_raw ( self, build: Filter ) -> Self:

        return self._fork_(filters=(*self._state.filters, build))

    def where_key ( self, key: object ) -> Self:

        return self.where(self._model.primary, key)

    def where_keys ( self, keys: Iterable[object] ) -> Self:

        return self.where_in(self._model.primary, keys)

    def order_by ( self, column: str, direction: str = "asc" ) -> Self:

        if direction not in ORDERS: raise Fault(Code.INTERNAL, reason=f"database.order.{direction}")

        return self._fork_(orders=(*self._state.orders, (column, direction)), random=False)

    def order_by_desc ( self, column: str ) -> Self:

        return self.order_by(column, "desc")

    def latest ( self, column: str = "created_at" ) -> Self:

        return self.order_by(column, "desc")

    def oldest ( self, column: str = "created_at" ) -> Self:

        return self.order_by(column, "asc")

    def in_random_order ( self ) -> Self:

        return self._fork_(orders=(), random=True)

    def reorder ( self, column: str | None = None, direction: str = "asc" ) -> Self:

        cleared = self._fork_(orders=(), random=False)

        return cleared.order_by(column, direction) if column else cleared

    def limit ( self, count: int ) -> Self:

        return self._fork_(limit=max(int(count), 0))

    def offset ( self, count: int ) -> Self:

        return self._fork_(offset=max(int(count), 0))

    def take ( self, count: int ) -> Self:

        return self.limit(count)

    def skip ( self, count: int ) -> Self:

        return self.offset(count)

    def for_page ( self, page: int, limit: int = 20 ) -> Self:

        return self.limit(limit).offset(max(page - 1, 0) * limit)

    def select ( self, *columns: str ) -> Self:

        return self._fork_(picked=columns)

    def distinct ( self ) -> Self:

        return self._fork_(distinct=True)

    def with_ ( self, *names: str ) -> Self:

        for name in names: self._model.relation_named(name)

        fresh = tuple(name for name in names if name not in self._state.loads)

        return self._fork_(loads=(*self._state.loads, *fresh))

    def without ( self, *names: str ) -> Self:

        return self._fork_(loads=tuple(name for name in self._state.loads if name not in names))

    def with_trashed ( self ) -> Self:

        return self._fork_(trash="all")

    def only_trashed ( self ) -> Self:

        return self._fork_(trash="trashed")

    def lock_for_update ( self ) -> Self:

        return self._fork_(lock="update")

    def shared_lock ( self ) -> Self:

        return self._fork_(lock="share")

    def scoped ( self, where: Values ) -> Self:

        return self.where_all(**dict(where))

    def columns ( self ) -> Sequence[str]:

        return self._model.columns()
