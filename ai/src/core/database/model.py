from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, override

from core.error import Code, Fault

KINDS = ("belongs_to", "has_one", "has_many", "belongs_to_many", "morph_many", "morph_to")

COLUMNS: dict[type, tuple[str, ...]] = {}

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
