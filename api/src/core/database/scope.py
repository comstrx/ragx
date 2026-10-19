from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Self

from core.error import Code, Fault
from sqlalchemy.sql import ColumnElement, TableClause
from .engine import Database
from .model import Model
from .session import Session
import sqlalchemy as sa

type Filter = Callable[[TableClause], ColumnElement[bool]]
type Builder = Callable[[Any, Any], ColumnElement[bool]]
type Values = Mapping[str, object]
type Condition = tuple[str, object] | tuple[str, str, object]
type Refine = Callable[[Any], Any]

PAIR    = 2
TRIPLE  = 3
TABLES  : dict[type[Model], TableClause] = {}
ORDERS  = ("asc", "desc")
LOCKS   = ("update", "share")

def plain ( value: object ) -> object:

    return sa.bindparam(None, value, type_=sa.types.NullType()) if isinstance(value, str) else value

def listed ( value: object ) -> list[object]:

    if isinstance(value, Iterable) and not isinstance(value, str | bytes): return [plain(item) for item in value]

    return [plain(value)]

def table_of ( model: type[Model] ) -> TableClause:

    known = TABLES.get(model)

    if known is None: known = TABLES[model] = sa.table(model.table, *(sa.column(name) for name in model.columns()))

    return known

BUILDERS: dict[str, Builder] = {
    "="         : lambda field, value: field.is_(None) if value is None else field == plain(value),
    "!="        : lambda field, value: field.is_not(None) if value is None else field != plain(value),
    "<>"        : lambda field, value: field.is_not(None) if value is None else field != plain(value),
    ">"         : lambda field, value: field > plain(value),
    ">="        : lambda field, value: field >= plain(value),
    "<"         : lambda field, value: field < plain(value),
    "<="        : lambda field, value: field <= plain(value),
    "like"      : lambda field, value: field.like(plain(str(value))),
    "not like"  : lambda field, value: field.not_like(plain(str(value))),
    "ilike"     : lambda field, value: field.ilike(plain(str(value))),
    "not ilike" : lambda field, value: field.not_ilike(plain(str(value))),
    "in"        : lambda field, value: field.in_(listed(value)),
    "not in"    : lambda field, value: field.not_in(listed(value)),
    "between"   : lambda field, value: field.between(plain(value[0]), plain(value[1])),
    "contains"  : lambda field, value: field.contains(value),
}

def clause ( column: str, operator: str, value: object ) -> Filter:

    builder = BUILDERS.get(operator.lower())

    if builder is None: raise Fault(Code.INTERNAL, reason="database.operator")

    def build ( table: TableClause ) -> ColumnElement[bool]:

        return builder(table.c[column], value)

    return build

def condition ( item: Condition ) -> Filter:

    parts = tuple(item)

    if len(parts) == PAIR: return clause(str(parts[0]), "=", parts[1])
    if len(parts) == TRIPLE: return clause(str(parts[0]), str(parts[1]), parts[2])

    raise Fault(Code.INTERNAL, reason="database.condition")

@dataclass(frozen=True, slots=True)
class State:

    filters  : tuple[Filter, ...] = ()
    orders   : tuple[tuple[str, str], ...] = ()
    loads    : tuple[str, ...] = ()
    picked   : tuple[str, ...] = ()
    limit    : int | None = None
    offset   : int | None = None
    trash    : str = "alive"
    distinct : bool = False
    random   : bool = False
    lock     : str | None = None

class Scope[M: Model]:

    def __init__ (
        self, model: type[M], database: Database, session: Session | None = None, state: State | None = None,
    ) -> None:

        self._model    = model
        self._database = database
        self._session  = session
        self._state    = state or State()
        self._table    = table_of(model)

    def model ( self ) -> type[M]:

        return self._model

    def state ( self ) -> State:

        return self._state

    def clone ( self ) -> Self:

        return self._fork_()

    def within ( self, session: Session ) -> Self:

        return type(self)(self._model, self._database, session, self._state)

    def tap ( self, refine: Refine ) -> Self:

        result = refine(self)

        return result if isinstance(result, type(self)) else self

    def when ( self, condition: object, refine: Refine, otherwise: Refine | None = None ) -> Self:

        if condition: return self.tap(refine)
        if otherwise is not None: return self.tap(otherwise)

        return self

    def unless ( self, condition: object, refine: Refine ) -> Self:

        return self.when(not condition, refine)

    def to_sql ( self ) -> str:

        dialect = self._database.dialect() if self._database.ready() else None

        return str(self._statement_().compile(dialect=dialect))

    def dump ( self ) -> dict[str, Any]:

        return {
            "table"   : self._model.table,
            "filters" : len(self._state.filters),
            "orders"  : list(self._state.orders),
            "loads"   : list(self._state.loads),
            "picked"  : list(self._state.picked),
            "limit"   : self._state.limit,
            "offset"  : self._state.offset,
            "trash"   : self._state.trash,
        }

    def _fork_ ( self, **changes: Any ) -> Self:

        return type(self)(self._model, self._database, self._session, replace(self._state, **changes))

    def _where_ ( self, trash: str | None = None ) -> list[ColumnElement[bool]]:

        mode  = trash or self._state.trash
        built = [build(self._table) for build in self._state.filters]

        if self._model.soft and "deleted_at" in self._model.columns():

            if mode == "alive": built.append(self._table.c["deleted_at"].is_(None))
            if mode == "trashed": built.append(self._table.c["deleted_at"].is_not(None))

        return built

    def _order_ ( self ) -> list[ColumnElement[Any]]:

        if self._state.random: return [sa.func.random()]

        return [
            self._table.c[column].desc() if direction == "desc" else self._table.c[column].asc()
            for column, direction in self._state.orders
        ]

    def _statement_ ( self ) -> Any:

        picked    = [self._table.c[name] for name in self._state.picked] if self._state.picked else list(self._table.c)
        statement = sa.select(*picked).where(*self._where_()).order_by(*self._order_())

        if self._state.distinct: statement = statement.distinct()
        if self._state.limit is not None: statement = statement.limit(self._state.limit)
        if self._state.offset: statement = statement.offset(self._state.offset)
        if self._state.lock == "update": statement = statement.with_for_update()
        if self._state.lock == "share": statement = statement.with_for_update(read=True)

        return statement
