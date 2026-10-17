from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum as Choices
from typing import Any, Self

from core.exceptions import Code, Fault
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateColumn, DropTable
import sqlalchemy as sa
from .engine import Session

type Define = Callable[["Blueprint"], None]

ACTIONS = {
    "cascade": "CASCADE", "restrict": "RESTRICT", "null": "SET NULL", "default": "SET DEFAULT", "none": "NO ACTION",
}
KINDS   = ("uuid", "increments")
METHODS = ("btree", "hash", "gin", "gist", "brin", "spgist")

@dataclass(slots=True)
class Column:

    name      : str
    type      : Any
    null      : bool = False
    fallback  : Any = None
    primary   : bool = False
    unique_   : bool = False
    indexed   : bool = False
    reference : tuple[str, str, str, str] | None = None

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

    def references (
        self, table: str, column: str = "id", on_delete: str = "cascade", on_update: str = "none",
    ) -> Self:

        if on_delete not in ACTIONS or on_update not in ACTIONS: raise ValueError((on_delete, on_update))

        self.reference = (table, column, ACTIONS[on_delete], ACTIONS[on_update])

        return self

@dataclass(frozen=True, slots=True)
class Indexed:

    columns : tuple[str, ...]
    unique  : bool = False
    name    : str | None = None
    where   : str | None = None
    method  : str | None = None
    include : tuple[str, ...] = ()

@dataclass(slots=True)
class Blueprint:

    table    : str
    columns  : list[Column] = field(default_factory=list)
    indexes  : list[Indexed] = field(default_factory=list)
    dropped  : list[str] = field(default_factory=list)
    renamed  : list[tuple[str, str]] = field(default_factory=list)
    unindex  : list[str] = field(default_factory=list)
    checks   : list[tuple[str, str | None]] = field(default_factory=list)
    keys     : list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    released : list[str] = field(default_factory=list)
    reindexed: list[tuple[str, str]] = field(default_factory=list)
    unforeign: list[str] = field(default_factory=list)

    def column ( self, name: str, kind: Any ) -> Column:

        column = Column(name, kind)

        self.columns.append(column)

        return column

    def id ( self, name: str = "id", kind: str = "uuid" ) -> Column:

        if kind not in KINDS: raise ValueError(kind)
        if kind == "uuid": return self.column(name, sa.Uuid(as_uuid=True)).key()

        return self.column(name, sa.BigInteger().with_variant(sa.Integer(), "sqlite")).key()

    def uuid ( self, name: str ) -> Column:
        return self.column(name, sa.Uuid(as_uuid=True))

    def string ( self, name: str, length: int = 255 ) -> Column:
        return self.column(name, sa.String(length))

    def text ( self, name: str ) -> Column:
        return self.column(name, sa.Text())

    def integer ( self, name: str ) -> Column:
        return self.column(name, sa.Integer())

    def big_integer ( self, name: str ) -> Column:
        return self.column(name, sa.BigInteger())

    def small_integer ( self, name: str ) -> Column:
        return self.column(name, sa.SmallInteger())

    def boolean ( self, name: str ) -> Column:
        return self.column(name, sa.Boolean()).default(sa.false())

    def float ( self, name: str ) -> Column:
        return self.column(name, sa.Float())

    def decimal ( self, name: str, precision: int = 12, scale: int = 2 ) -> Column:
        return self.column(name, sa.Numeric(precision, scale))

    def json ( self, name: str ) -> Column:
        return self.column(name, sa.JSON().with_variant(JSONB(), "postgresql"))

    def date ( self, name: str ) -> Column:
        return self.column(name, sa.Date())

    def timestamp ( self, name: str ) -> Column:
        return self.column(name, sa.DateTime(timezone=True))

    def timestamps ( self ) -> None:

        self.timestamp("created_at").default(sa.func.now())
        self.timestamp("updated_at").default(sa.func.now())

    def soft_deletes ( self ) -> Column:
        return self.timestamp("deleted_at").nullable()

    def enum ( self, name: str, choices: Sequence[str] | type[Choices], kind: str | None = None ) -> Column:

        values = [member.value for member in choices] if isinstance(choices, type) else list(choices)
        label  = kind or f"{self.table}_{name}"

        kind_ = sa.Enum(*values, name=label, native_enum=True, create_constraint=True, validate_strings=True)

        return self.column(name, kind_)

    def foreign (
        self, name: str, table: str, column: str = "id", on_delete: str = "cascade", kind: str = "uuid",
    ) -> Column:

        owner = self.uuid(name) if kind == "uuid" else self.big_integer(name)

        return owner.references(table, column, on_delete).index()

    def morphs ( self, name: str, kind: str = "uuid" ) -> None:

        self.string(f"{name}_type", 120)

        if kind == "uuid": self.uuid(f"{name}_id")
        else: self.big_integer(f"{name}_id")

        self.index([f"{name}_type", f"{name}_id"])

    def index (
        self, columns: Sequence[str] | str, unique: bool = False, name: str | None = None, where: str | None = None,
        method: str | None = None, include: Sequence[str] = (),
    ) -> None:

        if method is not None and method not in METHODS: raise ValueError(method)

        names = (columns,) if isinstance(columns, str) else tuple(columns)

        self.indexes.append(Indexed(names, unique, name, where, method, tuple(include)))

    def unique (
        self, columns: Sequence[str] | str, name: str | None = None, where: str | None = None,
        include: Sequence[str] = (),
    ) -> None:
        self.index(columns, unique=True, name=name, where=where, include=include)

    def gin ( self, columns: Sequence[str] | str, name: str | None = None, where: str | None = None ) -> None:
        self.index(columns, name=name, where=where, method="gin")

    def fulltext ( self, columns: Sequence[str] | str, name: str | None = None, language: str = "english" ) -> None:

        names  = (columns,) if isinstance(columns, str) else tuple(columns)
        joined = " || ' ' || ".join(f"coalesce(\"{column}\", '')" for column in names)

        label = name or f"{self.table}_{'_'.join(names)}_fulltext"

        self.index(f"to_tsvector('{language}', {joined})", name=label, method="gin")

    def primary ( self, columns: Sequence[str] | str, name: str | None = None ) -> None:

        names = (columns,) if isinstance(columns, str) else tuple(columns)

        self.keys.append((names, name))

    def check ( self, expression: str, name: str | None = None ) -> None:
        self.checks.append((expression, name))

    def drop_unique ( self, name: str ) -> None:

        self.released.append(name)
        self.unindex.append(name)

    def drop_check ( self, name: str ) -> None:
        self.released.append(name)

    def drop_primary ( self ) -> None:
        self.released.append(f"{self.table}_pkey")

    def drop_foreign ( self, column: str ) -> None:
        self.unforeign.append(column)

    def rename_index ( self, old: str, new: str ) -> None:
        self.reindexed.append((old, new))

    def drop_column ( self, name: str ) -> None:
        self.dropped.append(name)

    def rename_column ( self, old: str, new: str ) -> None:
        self.renamed.append((old, new))

    def drop_index ( self, name: str ) -> None:
        self.unindex.append(name)

    def index_name ( self, index: Indexed ) -> str:

        plain = "_".join("".join(part if part.isalnum() else "_" for part in column) for column in index.columns)

        return index.name or f"{self.table}_{plain}_{'unique' if index.unique else 'index'}".replace("__", "_")

    def build ( self, metadata: sa.MetaData ) -> sa.Table:

        for column in self.columns: self._target_(column, metadata)

        columns = [self._column_(column) for column in self.columns]
        extras  = [sa.CheckConstraint(expression, name=name) for expression, name in self.checks]
        keys    = [sa.PrimaryKeyConstraint(*names, name=name) for names, name in self.keys]

        return sa.Table(self.table, metadata, *columns, *keys, *extras)

    def _target_ ( self, column: Column, metadata: sa.MetaData ) -> None:

        if column.reference is None or column.reference[0] == self.table: return
        if column.reference[0] in metadata.tables: return

        sa.Table(column.reference[0], metadata, sa.Column(column.reference[1], column.type))

    def _column_ ( self, column: Column ) -> sa.Column[Any]:

        target  = column.reference
        foreign = [sa.ForeignKey(f"{target[0]}.{target[1]}", ondelete=target[2], onupdate=target[3])] if target else []

        return sa.Column(
            column.name, column.type, *foreign, primary_key=column.primary, nullable=column.null and not column.primary,
            unique=column.unique_ or None, index=column.indexed or None,
            server_default=self._default_(column.fallback),
        )

    def _default_ ( self, value: object ) -> Any:

        if value is None: return None
        if isinstance(value, bool): return sa.true() if value else sa.false()
        if isinstance(value, int | float): return sa.text(str(value))
        if isinstance(value, str): return value

        return value

class Schema:

    def __init__ ( self, session: Session ) -> None:

        self._session = session

    def quote ( self, name: str ) -> str:
        return self._session.dialect().identifier_preparer.quote(name)

    async def create ( self, table: str, define: Define ) -> None:

        blueprint = Blueprint(table)

        define(blueprint)

        built = blueprint.build(sa.MetaData())

        await self._session.sync(lambda connection: built.create(connection, checkfirst=True))

        for index in blueprint.indexes: await self._index_(blueprint, index)

    async def table ( self, table: str, define: Define ) -> None:

        blueprint = Blueprint(table)

        define(blueprint)

        name = self.quote(table)

        for old, new in blueprint.renamed:
            await self._session.script(f"ALTER TABLE {name} RENAME COLUMN {self.quote(old)} TO {self.quote(new)}")

        for dropped in blueprint.dropped:
            await self._session.script(f"ALTER TABLE {name} DROP COLUMN IF EXISTS {self.quote(dropped)}")

        for column in blueprint.columns: await self._add_(table, column)

        for index in blueprint.indexes: await self._index_(blueprint, index)

        await self._constrain_(blueprint)
        await self._release_(blueprint)

    async def _constrain_ ( self, blueprint: Blueprint ) -> None:

        name = self.quote(blueprint.table)

        for expression, label in blueprint.checks:

            constraint = self.quote(label or f"{blueprint.table}_check")

            await self._session.script(f"ALTER TABLE {name} ADD CONSTRAINT {constraint} CHECK ({expression})")

        for columns, label in blueprint.keys:

            constraint = self.quote(label or f"{blueprint.table}_pkey")
            listed     = ", ".join(self.quote(column) for column in columns)

            await self._session.script(f"ALTER TABLE {name} ADD CONSTRAINT {constraint} PRIMARY KEY ({listed})")

    async def _release_ ( self, blueprint: Blueprint ) -> None:

        name = self.quote(blueprint.table)

        for key in blueprint.unforeign:

            constraint = self.quote(f"{blueprint.table}_{key}_fkey")

            await self._session.script(f"ALTER TABLE {name} DROP CONSTRAINT IF EXISTS {constraint}")

        for released in blueprint.released:
            await self._session.script(f"ALTER TABLE {name} DROP CONSTRAINT IF EXISTS {self.quote(released)}")

        for dropped in blueprint.unindex: await self._session.script(f"DROP INDEX IF EXISTS {self.quote(dropped)}")

        for old, new in blueprint.reindexed:
            await self._session.script(f"ALTER INDEX IF EXISTS {self.quote(old)} RENAME TO {self.quote(new)}")

    async def drop ( self, table: str ) -> None:

        placeholder = sa.Table(table, sa.MetaData())

        await self._session.execute(DropTable(placeholder, if_exists=True))

    async def rename ( self, old: str, new: str ) -> None:
        await self._session.script(f"ALTER TABLE {self.quote(old)} RENAME TO {self.quote(new)}")

    async def has ( self, table: str ) -> bool:
        return await self._session.sync(lambda connection: bool(sa.inspect(connection).has_table(table)))

    async def columns ( self, table: str ) -> list[str]:

        found = await self._session.sync(lambda connection: sa.inspect(connection).get_columns(table))

        return [str(column["name"]) for column in found]

    async def truncate ( self, table: str ) -> None:
        await self._session.truncate(table)

    async def _add_ ( self, table: str, column: Column ) -> None:

        built = Blueprint(table)._column_(column)
        spec  = str(CreateColumn(built).compile(dialect=self._session.dialect()))

        if isinstance(column.type, sa.Enum):
            await self._session.sync(lambda connection: column.type.create(connection, checkfirst=True))

        await self._session.script(f"ALTER TABLE {self.quote(table)} ADD COLUMN IF NOT EXISTS {spec}")

        if column.reference:

            target, key, on_delete, on_update = column.reference
            constraint = self.quote(f"{table}_{column.name}_fkey")

            await self._session.script(
                f"ALTER TABLE {self.quote(table)} ADD CONSTRAINT {constraint} FOREIGN KEY ({self.quote(column.name)}) "
                f"REFERENCES {self.quote(target)} ({self.quote(key)}) ON DELETE {on_delete} ON UPDATE {on_update}",
            )

        if column.indexed or column.unique_:
            await self._index_(Blueprint(table), Indexed((column.name,), column.unique_))

    async def _index_ ( self, blueprint: Blueprint, index: Indexed ) -> None:

        columns = ", ".join(column if "(" in column else self.quote(column) for column in index.columns)
        unique  = "UNIQUE " if index.unique else ""
        method  = f" USING {index.method}" if index.method else ""
        include = f" INCLUDE ({', '.join(self.quote(column) for column in index.include)})" if index.include else ""
        where   = f" WHERE {index.where}" if index.where else ""
        name    = self.quote(blueprint.index_name(index))
        target  = self.quote(blueprint.table)

        await self._session.script(
            f"CREATE {unique}INDEX IF NOT EXISTS {name} ON {target}{method} ({columns}){include}{where}",
        )

    async def indexes ( self, table: str ) -> list[str]:

        rows = await self._session.fetch(
            sa.text("SELECT indexname FROM pg_indexes WHERE tablename = :table ORDER BY indexname"), { "table": table },
        )

        return [str(row["indexname"]) for row in rows]

    async def constraints ( self, table: str ) -> list[str]:

        rows = await self._session.fetch(
            sa.text("SELECT conname FROM pg_constraint WHERE conrelid = CAST(:table AS regclass) ORDER BY conname"),
            { "table": table },
        )

        return [str(row["conname"]) for row in rows]

    def require ( self, condition: bool, reason: str ) -> None:

        if not condition: raise Fault(Code.INTERNAL, reason=reason)
