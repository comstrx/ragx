from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, override

from core.error import Code, Fault
from .session import Session
import sqlalchemy as sa

KINDS = ("belongs_to", "has_one", "has_many", "belongs_to_many", "morph_many", "morph_to")

COLUMNS: dict[type, tuple[str, ...]] = {}
type Work = Callable[[Session], Awaitable[Any]]
type Runner = Callable[[Work], Awaitable[Any]]

@dataclass(frozen=True, slots=True)
class Relation:

    kind          : str
    related       : str | None = None
    foreign       : str | None = None
    local         : str = "id"
    pivot         : str | None = None
    pivot_foreign : str | None = None
    pivot_related : str | None = None
    morph         : str | None = None

    def many ( self ) -> bool:

        return self.kind in ("has_many", "belongs_to_many", "morph_many")

def named ( related: str | type ) -> str:

    return related if isinstance(related, str) else related.__name__

def belongs_to ( related: str | type, foreign: str | None = None, owner: str = "id" ) -> Relation:

    return Relation("belongs_to", named(related), foreign, owner)

def has_one ( related: str | type, foreign: str | None = None, local: str = "id" ) -> Relation:

    return Relation("has_one", named(related), foreign, local)

def has_many ( related: str | type, foreign: str | None = None, local: str = "id" ) -> Relation:

    return Relation("has_many", named(related), foreign, local)

def belongs_to_many (
    related: str | type, pivot: str, foreign: str | None = None, related_key: str | None = None, local: str = "id",
) -> Relation:

    return Relation("belongs_to_many", named(related), None, local, pivot, foreign, related_key)

def morph_many ( related: str | type, name: str, local: str = "id" ) -> Relation:

    return Relation("morph_many", named(related), None, local, morph=name)

def morph_to ( name: str ) -> Relation:

    return Relation("morph_to", None, None, "id", morph=name)

@dataclass(frozen=True, slots=True, kw_only=True)
class Model:

    table      : ClassVar[str] = ""
    primary    : ClassVar[str] = "id"
    soft       : ClassVar[bool] = True
    timestamps : ClassVar[bool] = True
    morph_name : ClassVar[str] = ""
    relations  : ClassVar[Mapping[str, Relation]] = {}
    registry   : ClassVar[dict[str, type[Model]]] = {}

    related: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    @override
    def __init_subclass__ ( cls, **kwargs: object ) -> None:

        super().__init_subclass__(**kwargs)

        Model.registry[cls.__name__] = cls

        if not cls.morph_name: cls.morph_name = cls.table

    @classmethod
    def columns ( cls ) -> tuple[str, ...]:

        known = COLUMNS.get(cls)

        if known is None: known = COLUMNS[cls] = tuple(entry.name for entry in fields(cls) if entry.name != "related")

        return known

    @classmethod
    def relation_named ( cls, name: str ) -> Relation:

        relation = cls.relations.get(name)

        if relation is None: raise Fault(Code.INTERNAL, reason=f"{cls.__name__}.{name}")

        return relation

    @classmethod
    def resolve ( cls, name: str ) -> type[Model]:

        found = cls.registry.get(name)

        if found is None: raise Fault(Code.INTERNAL, reason=f"model.{name}")

        return found

    @classmethod
    def foreign_name ( cls ) -> str:

        return f"{cls.morph_name.rstrip('s') if cls.morph_name.endswith('s') else cls.morph_name}_id"

    def key ( self ) -> Any:

        return getattr(self, self.primary)

    def relation ( self, name: str ) -> Any:

        if name not in self.related: raise Fault(Code.INTERNAL, reason=f"{type(self).__name__}.{name}.unloaded")

        return self.related[name]

    def attach ( self, name: str, value: object ) -> None:

        self.related[name] = value

    def dump ( self ) -> dict[str, Any]:

        return { name: getattr(self, name) for name in self.columns() }

class Pivot:

    __slots__ = ("_owner", "_related", "_run", "_table")

    def __init__ ( self, model: type[Model], name: str, run: Runner ) -> None:

        relation = model.relation_named(name)

        if relation.kind != "belongs_to_many" or not relation.pivot:
            raise Fault(Code.INTERNAL, reason=f"database.pivot.{name}")

        related       = model.resolve(relation.related or "")
        self._owner   = relation.pivot_foreign or model.foreign_name()
        self._related = relation.pivot_related or related.foreign_name()
        self._table   = relation.pivot
        self._run     = run

    def table ( self, *extra: str ) -> sa.TableClause:

        return sa.table(self._table, *(sa.column(name) for name in (self._owner, self._related, *extra)))

    async def keys ( self, owner: object ) -> list[Any]:

        pivot     = self.table()
        statement = sa.select(pivot.c[self._related]).where(pivot.c[self._owner] == owner)
        rows      = await self._run(lambda session: session.fetch(statement))

        return [row[self._related] for row in rows]

    async def has ( self, owner: object, related: object ) -> bool:

        return str(related) in { str(key) for key in await self.keys(owner) }

    async def attach ( self, owner: object, *related: object, values: Mapping[str, object] | None = None ) -> int:

        known   = { str(key) for key in await self.keys(owner) }
        fresh   = list(dict.fromkeys(item for item in related if str(item) not in known))
        extra   = dict(values or {})
        pivot   = self.table(*extra)
        payload = [{ self._owner: owner, self._related: item, **extra } for item in fresh]

        if not payload: return 0

        return int(await self._run(lambda session: session.execute(sa.insert(pivot).values(payload))))

    async def detach ( self, owner: object, *related: object ) -> int:

        pivot     = self.table()
        statement = sa.delete(pivot).where(pivot.c[self._owner] == owner)

        if related: statement = statement.where(pivot.c[self._related].in_(list(related)))

        return int(await self._run(lambda session: session.execute(statement)))

    async def sync ( self, owner: object, related: Iterable[object], detaching: bool = True ) -> dict[str, list[str]]:

        wanted  = { str(item): item for item in related }
        known   = { str(key): key for key in await self.keys(owner) }
        missing = [wanted[key] for key in wanted if key not in known]
        extra   = [known[key] for key in known if key not in wanted] if detaching else []

        await self.attach(owner, *missing)

        if extra: await self.detach(owner, *extra)

        return { "attached": sorted(str(item) for item in missing), "detached": sorted(str(item) for item in extra) }

    async def toggle ( self, owner: object, *related: object ) -> dict[str, list[str]]:

        known   = { str(key) for key in await self.keys(owner) }
        present = [item for item in related if str(item) in known]
        absent  = [item for item in related if str(item) not in known]

        if present: await self.detach(owner, *present)

        await self.attach(owner, *absent)

        return { "attached": sorted(str(item) for item in absent), "detached": sorted(str(item) for item in present) }
