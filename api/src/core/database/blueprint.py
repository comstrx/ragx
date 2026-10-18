from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum as Choices
from typing import Any

from sqlalchemy.dialects.postgresql import ARRAY, INET, INTERVAL, JSONB
import sqlalchemy as sa
from .column import Column, Indexed

KINDS   = ("uuid", "increments")
METHODS = ("btree", "hash", "gin", "gist", "brin", "spgist")

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
    note     : str | None = None

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

    def char ( self, name: str, length: int = 36 ) -> Column:
        return self.column(name, sa.CHAR(length))

    def text ( self, name: str ) -> Column:
        return self.column(name, sa.Text())

    def binary ( self, name: str ) -> Column:
        return self.column(name, sa.LargeBinary())

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

    def array ( self, name: str, kind: Any = None ) -> Column:
        return self.column(name, ARRAY(kind or sa.String()))

    def inet ( self, name: str ) -> Column:
        return self.column(name, INET())

    def interval ( self, name: str ) -> Column:
        return self.column(name, INTERVAL())

    def date ( self, name: str ) -> Column:
        return self.column(name, sa.Date())

    def time ( self, name: str ) -> Column:
        return self.column(name, sa.Time(timezone=True))

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

    def brin ( self, columns: Sequence[str] | str, name: str | None = None ) -> None:
        self.index(columns, name=name, method="brin")

    def fulltext ( self, columns: Sequence[str] | str, name: str | None = None, language: str = "english" ) -> None:

        names  = (columns,) if isinstance(columns, str) else tuple(columns)
        joined = " || ' ' || ".join(f"coalesce(\"{column}\", '')" for column in names)
        label  = name or f"{self.table}_{'_'.join(names)}_fulltext"

        self.index(f"to_tsvector('{language}', {joined})", name=label, method="gin")

    def primary ( self, columns: Sequence[str] | str, name: str | None = None ) -> None:

        names = (columns,) if isinstance(columns, str) else tuple(columns)

        self.keys.append((names, name))

    def check ( self, expression: str, name: str | None = None ) -> None:
        self.checks.append((expression, name))

    def comment ( self, text: str ) -> None:
        self.note = text

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

    def drop_column ( self, *names: str ) -> None:
        self.dropped.extend(names)

    def drop_timestamps ( self ) -> None:
        self.drop_column("created_at", "updated_at")

    def drop_soft_deletes ( self ) -> None:
        self.drop_column("deleted_at")

    def drop_morphs ( self, name: str ) -> None:
        self.drop_column(f"{name}_type", f"{name}_id")

    def rename_column ( self, old: str, new: str ) -> None:
        self.renamed.append((old, new))

    def drop_index ( self, name: str ) -> None:
        self.unindex.append(name)

    def index_name ( self, index: Indexed ) -> str:

        plain = "_".join("".join(part if part.isalnum() else "_" for part in column) for column in index.columns)

        return index.name or f"{self.table}_{plain}_{'unique' if index.unique else 'index'}".replace("__", "_")

    def build ( self, metadata: sa.MetaData ) -> sa.Table:

        for column in self.columns: self.target(column, metadata)

        columns = [column.build() for column in self.columns]
        extras  = [sa.CheckConstraint(expression, name=name) for expression, name in self.checks]
        keys    = [sa.PrimaryKeyConstraint(*names, name=name) for names, name in self.keys]

        return sa.Table(self.table, metadata, *columns, *keys, *extras, comment=self.note)

    def target ( self, column: Column, metadata: sa.MetaData ) -> None:

        if column.reference is None or column.reference[0] == self.table: return
        if column.reference[0] in metadata.tables: return

        sa.Table(column.reference[0], metadata, sa.Column(column.reference[1], column.type))
