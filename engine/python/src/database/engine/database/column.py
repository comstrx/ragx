from dataclasses import dataclass
from typing import Any, Self, override

from engine.error import Code, Fault
import sqlalchemy as sa

STORAGE = ("plain", "external", "extended", "main")
ACTIONS = {
    "cascade": "CASCADE", "restrict": "RESTRICT", "null": "SET NULL", "default": "SET DEFAULT", "none": "NO ACTION",
}

@dataclass(slots=True)
class Column:

    name      : str
    type      : Any
    null      : bool = False
    fallback  : Any = None
    primary   : bool = False
    unique_   : bool = False
    indexed   : bool = False
    note      : str | None = None
    computed  : str | None = None
    reference : tuple[str, str, str, str] | None = None
    storage   : str | None = None

    def nullable ( self, value: bool = True ) -> Self:

        self.null = value

        return self

    def default ( self, value: object ) -> Self:

        self.fallback = value

        return self

    def unique ( self ) -> Self:

        self.unique_ = True

        return self

    def index ( self ) -> Self:

        self.indexed = True

        return self

    def key ( self ) -> Self:

        self.primary = True

        return self

    def comment ( self, text: str ) -> Self:

        self.note = text

        return self

    def generated ( self, expression: str ) -> Self:

        self.computed = expression

        return self

    def stored ( self, mode: str ) -> Self:

        if mode not in STORAGE: raise Fault(Code.INTERNAL, reason=f"database.storage.{mode}")

        self.storage = mode

        return self

    def references (
        self, table: str, column: str = "id", on_delete: str = "cascade", on_update: str = "none",
    ) -> Self:

        if on_delete not in ACTIONS or on_update not in ACTIONS: raise Fault(Code.INTERNAL, reason="database.action")

        self.reference = (table, column, ACTIONS[on_delete], ACTIONS[on_update])

        return self

    def build ( self ) -> sa.Column[Any]:

        target  = self.reference
        foreign = [sa.ForeignKey(f"{target[0]}.{target[1]}", ondelete=target[2], onupdate=target[3])] if target else []
        derived = [sa.Computed(self.computed, persisted=True)] if self.computed else []

        return sa.Column(
            self.name, self.type, *foreign, *derived, primary_key=self.primary, nullable=self.null and not self.primary,
            unique=self.unique_ or None, index=self.indexed or None, server_default=self.server_default(),
            comment=self.note,
        )

    def server_default ( self ) -> Any:

        value = self.fallback

        if value is None: return None
        if isinstance(value, bool): return sa.true() if value else sa.false()
        if isinstance(value, int | float): return sa.text(str(value))

        return value

class Embedded(sa.types.UserDefinedType[str]):

    cache_ok: bool | None = True

    def __init__ ( self, dimension: int ) -> None:

        if dimension < 1: raise Fault(Code.INTERNAL, reason="database.vector.dimension")

        self.dimension = dimension

    @override
    def get_col_spec ( self, **_: Any ) -> str:

        return f"vector({self.dimension})"

@dataclass(frozen=True, slots=True)
class Indexed:

    columns : tuple[str, ...]
    unique  : bool = False
    name    : str | None = None
    where   : str | None = None
    method  : str | None = None
    include : tuple[str, ...] = ()
