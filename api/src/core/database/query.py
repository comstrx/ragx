from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Self

from core.array import Page, array
from core.date import date
from core.exceptions import Code, Fault
from core.rand import rand
from sqlalchemy.sql import ColumnElement, TableClause
import sqlalchemy as sa
from .engine import Database, Session
from .model import Model, Relation
from .rows import Rows

type Values = Mapping[str, object]
type Filter = Callable[[TableClause], ColumnElement[bool]]
type Builder = Callable[[Any, Any], ColumnElement[bool]]
type Work = Callable[[Session], Awaitable[Any]]

PAIR = 2
rows = Rows()
TABLES: dict[type[Model], TableClause] = {}

def listed ( value: object ) -> list[object]:

    if isinstance(value, Iterable) and not isinstance(value, str | bytes): return [plain(item) for item in value]

    return [plain(value)]

def table_of ( model: type[Model] ) -> TableClause:

    known = TABLES.get(model)

    if known is None: known = TABLES[model] = sa.table(model.table, *(sa.column(name) for name in model.columns()))

    return known

def plain ( value: object ) -> object:
    return sa.bindparam(None, value, type_=sa.types.NullType()) if isinstance(value, str) else value

BUILDERS: dict[str, Builder] = {
    "="      : lambda field, value: field.is_(None) if value is None else field == plain(value),
    "!="     : lambda field, value: field.is_not(None) if value is None else field != plain(value),
    "<>"     : lambda field, value: field.is_not(None) if value is None else field != plain(value),
    ">"      : lambda field, value: field > plain(value),
    ">="     : lambda field, value: field >= plain(value),
    "<"      : lambda field, value: field < plain(value),
    "<="     : lambda field, value: field <= plain(value),
    "like"   : lambda field, value: field.like(plain(str(value))),
    "ilike"  : lambda field, value: field.ilike(plain(str(value))),
    "in"     : lambda field, value: field.in_(listed(value)),
    "not in" : lambda field, value: field.not_in(listed(value)),
}

def clause ( column: str, operator: str, value: object ) -> Filter:

    builder = BUILDERS.get(operator)

    if builder is None: raise ValueError(operator)

    def build ( table: TableClause ) -> ColumnElement[bool]:
        return builder(table.c[column], value)

    return build

@dataclass(frozen=True, slots=True)
class State:

    filters : tuple[Filter, ...] = ()
    orders  : tuple[tuple[str, str], ...] = ()
    loads   : tuple[str, ...] = ()
    picked  : tuple[str, ...] = ()
    limit   : int | None = None
    offset  : int | None = None
    trash   : str = "alive"

class Query[M: Model]:

    def __init__ (
        self, model: type[M], database: Database, session: Session | None = None, state: State | None = None,
    ) -> None:

        self._model    = model
        self._database = database
        self._session  = session
        self._state    = state or State()
        self._table    = table_of(model)

    def where ( self, column: str, *args: object ) -> Self:

        if len(args) == 1: return self.where_raw(clause(column, "=", args[0]))
        if len(args) == PAIR and isinstance(args[0], str): return self.where_raw(clause(column, args[0], args[1]))

        raise ValueError(column)

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

    def where_between ( self, column: str, low: object, high: object ) -> Self:
        return self.where(column, ">=", low).where(column, "<=", high)

    def where_raw ( self, build: Filter ) -> Self:
        return self._fork_(filters=(*self._state.filters, build))

    def order_by ( self, column: str, direction: str = "asc" ) -> Self:

        if direction not in ("asc", "desc"): raise ValueError(direction)

        return self._fork_(orders=(*self._state.orders, (column, direction)))

    def latest ( self, column: str = "created_at" ) -> Self:
        return self.order_by(column, "desc")

    def oldest ( self, column: str = "created_at" ) -> Self:
        return self.order_by(column, "asc")

    def limit ( self, count: int ) -> Self:
        return self._fork_(limit=max(int(count), 0))

    def offset ( self, count: int ) -> Self:
        return self._fork_(offset=max(int(count), 0))

    def select ( self, *columns: str ) -> Self:
        return self._fork_(picked=columns)

    def with_ ( self, *names: str ) -> Self:

        for name in names: self._model.relation_named(name)

        fresh = tuple(name for name in names if name not in self._state.loads)

        return self._fork_(loads=(*self._state.loads, *fresh))

    def with_trashed ( self ) -> Self:
        return self._fork_(trash="all")

    def only_trashed ( self ) -> Self:
        return self._fork_(trash="trashed")

    async def get ( self ) -> list[M]:

        statement = self._statement_()
        found     = rows.many(self._model, await self._run_(lambda session: session.fetch(statement)))

        await self._load_(found)

        return found

    async def first ( self ) -> M | None:

        found = await self.limit(1).get()

        return found[0] if found else None

    async def first_or_fail ( self ) -> M:

        found = await self.first()

        if found is None: raise Fault(Code.NOT_FOUND, reason=self._model.table)

        return found

    async def find ( self, key: object ) -> M | None:
        return await self.where(self._model.primary, key).first()

    async def find_or_fail ( self, key: object ) -> M:
        return await self.where(self._model.primary, key).first_or_fail()

    async def count ( self ) -> int:

        statement = sa.select(sa.func.count()).select_from(self._table).where(*self._where_())
        value     = await self._run_(lambda session: session.value(statement))

        return int(value or 0)

    async def exists ( self ) -> bool:
        return await self.limit(1).count() > 0

    async def pluck ( self, column: str ) -> list[Any]:

        statement = sa.select(self._table.c[column]).where(*self._where_()).order_by(*self._order_())
        found     = await self._run_(lambda session: session.fetch(statement))

        return [row[column] for row in found]

    async def paginate ( self, page: int = 1, limit: int = 20 ) -> tuple[list[M], Page]:

        meta = array.page(await self.count(), page, limit)

        return await self.limit(meta["limit"]).offset(array.offset(meta["page"], meta["limit"])).get(), meta

    async def create ( self, values: Values ) -> M:

        payload   = self._stamp_(dict(values), creating=True)
        statement = sa.insert(self._table).values(**payload).returning(*self._table.c)
        row       = await self._run_(lambda session: session.row(statement))

        if row is None: raise Fault(Code.INTERNAL, reason=self._model.table)

        return rows.into(self._model, row)

    async def insert ( self, items: Sequence[Values] ) -> int:

        if not items: return 0

        payloads  = [self._stamp_(dict(values), creating=True) for values in items]
        statement = sa.insert(self._table).values(payloads)
        count     = await self._run_(lambda session: session.execute(statement))

        return int(count)

    async def update ( self, values: Values ) -> int:

        payload   = self._stamp_(dict(values), creating=False)
        statement = sa.update(self._table).where(*self._where_()).values(**payload)
        count     = await self._run_(lambda session: session.execute(statement))

        return int(count)

    async def delete ( self ) -> int:

        if self._model.soft and self._state.trash == "alive": return await self.update({ "deleted_at": date.now() })

        statement = sa.delete(self._table).where(*self._where_())
        count     = await self._run_(lambda session: session.execute(statement))

        return int(count)

    async def force_delete ( self ) -> int:

        statement = sa.delete(self._table).where(*self._where_(trash="all"))
        count     = await self._run_(lambda session: session.execute(statement))

        return int(count)

    async def restore ( self ) -> int:

        statement = sa.update(self._table).where(*self._where_(trash="trashed")).values(deleted_at=None)
        count     = await self._run_(lambda session: session.execute(statement))

        return int(count)

    def _stamp_ ( self, values: dict[str, object], creating: bool ) -> dict[str, object]:

        columns = self._model.columns()
        primary = self._model.primary
        now     = date.now()

        if creating and primary in columns and values.get(primary) is None: values[primary] = rand.uuid()
        if self._model.timestamps and "updated_at" in columns: values.setdefault("updated_at", now)
        if creating and self._model.timestamps and "created_at" in columns: values.setdefault("created_at", now)

        return values

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

        return [
            self._table.c[column].desc() if direction == "desc" else self._table.c[column].asc()
            for column, direction in self._state.orders
        ]

    def _statement_ ( self ) -> Any:

        picked    = [self._table.c[name] for name in self._state.picked] if self._state.picked else list(self._table.c)
        statement = sa.select(*picked).where(*self._where_()).order_by(*self._order_())

        if self._state.limit is not None: statement = statement.limit(self._state.limit)
        if self._state.offset: statement = statement.offset(self._state.offset)

        return statement

    async def _run_ ( self, work: Work ) -> Any:

        if self._session is not None: return await work(self._session)

        async with self._database.session() as session: return await work(session)

    async def _load_ ( self, found: list[M] ) -> None:

        for name in self._state.loads: await self._relate_(found, name, self._model.relation_named(name))

    async def _relate_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        if not found: return

        match relation.kind:
            case "belongs_to": await self._belongs_to_(found, name, relation)
            case "has_one" | "has_many": await self._has_(found, name, relation)
            case "belongs_to_many": await self._belongs_to_many_(found, name, relation)
            case "morph_many": await self._morph_many_(found, name, relation)
            case "morph_to": await self._morph_to_(found, name, relation)
            case _: raise Fault(Code.INTERNAL, reason=f"relation.{relation.kind}")

    def _related_ ( self, relation: Relation ) -> Query[Any]:
        return Query(self._model.resolve(relation.related or ""), self._database, self._session)

    async def _belongs_to_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        related = self._model.resolve(relation.related or "")
        foreign = relation.foreign or related.foreign_name()
        keys    = { getattr(item, foreign) for item in found if getattr(item, foreign) is not None }
        owners  = await self._related_(relation).where_in(relation.local, keys).get() if keys else []
        by_key  = { getattr(owner, relation.local): owner for owner in owners }

        for item in found: item.attach(name, by_key.get(getattr(item, foreign)))

    async def _has_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        foreign  = relation.foreign or self._model.foreign_name()
        keys     = { getattr(item, relation.local) for item in found }
        children = await self._related_(relation).where_in(foreign, keys).get()
        grouped  = array.group(children, lambda child: getattr(child, foreign))

        for item in found:

            own = grouped.get(getattr(item, relation.local), [])

            item.attach(name, own if relation.kind == "has_many" else (own[0] if own else None))

    async def _belongs_to_many_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        related = self._model.resolve(relation.related or "")
        mine    = relation.pivot_foreign or self._model.foreign_name()
        theirs  = relation.pivot_related or related.foreign_name()
        keys    = { getattr(item, relation.local) for item in found }
        bridge  = sa.table(relation.pivot or "", sa.column(mine), sa.column(theirs))
        linking = sa.select(bridge).where(bridge.c[mine].in_(list(keys)))
        links   = await self._run_(lambda session: session.fetch(linking))
        wanted  = { link[theirs] for link in links }
        others  = await self._related_(relation).where_in(related.primary, wanted).get() if wanted else []
        by_key  = { getattr(other, related.primary): other for other in others }
        grouped: dict[Any, list[Any]] = {}

        for link in links:

            other = by_key.get(link[theirs])

            if other is not None: grouped.setdefault(link[mine], []).append(other)

        for item in found: item.attach(name, grouped.get(getattr(item, relation.local), []))

    async def _morph_many_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        prefix   = relation.morph or ""
        keys     = { getattr(item, relation.local) for item in found }
        query    = self._related_(relation).where(f"{prefix}_type", self._model.morph_name)
        children = await query.where_in(f"{prefix}_id", keys).get()
        grouped  = array.group(children, lambda child: getattr(child, f"{prefix}_id"))

        for item in found: item.attach(name, grouped.get(getattr(item, relation.local), []))

    async def _morph_to_ ( self, found: list[M], name: str, relation: Relation ) -> None:

        prefix  = relation.morph or ""
        by_type = array.group(found, lambda item: str(getattr(item, f"{prefix}_type")))
        owners: dict[tuple[str, Any], Any] = {}

        for alias, items in by_type.items():

            model = next((entry for entry in Model.registry.values() if entry.morph_name == alias), None)

            if model is None: raise Fault(Code.INTERNAL, reason=f"morph.{alias}")

            keys  = { getattr(item, f"{prefix}_id") for item in items }
            heads = await Query(model, self._database, self._session).where_in(model.primary, keys).get()

            owners.update({ (alias, getattr(head, model.primary)): head for head in heads })

        for item in found:

            mark = (str(getattr(item, f"{prefix}_type")), getattr(item, f"{prefix}_id"))

            item.attach(name, owners.get(mark))
