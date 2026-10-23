from collections.abc import Callable

from engine.error import Code, Fault
from sqlalchemy.schema import CreateColumn, DropTable
from .blueprint import Blueprint
from .column import Column, Indexed
from .session import SETTING, Session
import sqlalchemy as sa

type Define = Callable[[Blueprint], None]

class Schema:

    def __init__ ( self, session: Session ) -> None:

        self._session = session

    def quote ( self, name: str ) -> str:

        return self._session.dialect().identifier_preparer.quote(name)

    async def extension ( self, name: str ) -> None:

        if not name.replace("_", "").isalnum(): raise Fault(Code.INTERNAL, reason="database.extension")

        await self._session.script(f"CREATE EXTENSION IF NOT EXISTS {self.quote(name)}")

    async def analyze ( self, table: str ) -> None:

        await self._session.script(f"ANALYZE {self.quote(table)}")

    async def extended ( self, name: str ) -> bool:

        found = sa.text("SELECT 1 FROM pg_extension WHERE extname = :name")

        return await self._session.value(found, { "name": name }) is not None

    async def create ( self, table: str, define: Define ) -> None:

        blueprint = Blueprint(table)

        define(blueprint)

        built = blueprint.build(sa.MetaData())

        await self._session.sync(lambda connection: built.create(connection, checkfirst=True))

        for column in blueprint.columns: await self.store(blueprint.table, column)
        for index in blueprint.indexes: await self.add_index(blueprint, index)

        if blueprint.isolation is not None: await self.isolate(blueprint.table, *blueprint.isolation)

    async def store ( self, table: str, column: Column ) -> None:

        if column.storage is None: return

        target = f"{self.quote(table)} ALTER COLUMN {self.quote(column.name)}"

        await self._session.script(f"ALTER TABLE {target} SET STORAGE {column.storage.upper()}")

    async def create_if_missing ( self, table: str, define: Define ) -> bool:

        if await self.has(table): return False

        await self.create(table, define)

        return True

    async def table ( self, table: str, define: Define ) -> None:

        blueprint = Blueprint(table)

        define(blueprint)

        name = self.quote(table)

        for old, new in blueprint.renamed:
            await self._session.script(f"ALTER TABLE {name} RENAME COLUMN {self.quote(old)} TO {self.quote(new)}")

        for dropped in blueprint.dropped:
            await self._session.script(f"ALTER TABLE {name} DROP COLUMN IF EXISTS {self.quote(dropped)}")

        for column in blueprint.columns: await self.add_column(table, column)

        for index in blueprint.indexes: await self.add_index(blueprint, index)

        await self.constrain(blueprint)
        await self.release(blueprint)

        if blueprint.note is not None: await self.comment(table, blueprint.note)
        if blueprint.isolation is not None: await self.isolate(table, *blueprint.isolation)

    async def isolate ( self, table: str, column: str = "tenant_id", setting: str = "app.tenant" ) -> None:

        found = sa.text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = to_regclass(:table) AND attname = :column AND NOT attisdropped",
        )
        kind  = await self._session.value(found, { "table": self.quote(table), "column": column })

        self.require(SETTING.fullmatch(setting) is not None, "database.isolate.setting")
        self.require(kind is not None, "database.isolate.column")

        policy = self.quote(f"{table}_isolation")

        for sql in self._session.adapter().isolate(self.quote(table), self.quote(column), setting, str(kind), policy):
            await self._session.script(sql)

    async def share ( self, table: str ) -> None:

        for sql in self._session.adapter().share(self.quote(table), self.quote(f"{table}_isolation")):
            await self._session.script(sql)

    async def isolated ( self, table: str ) -> bool:

        found = sa.text(
            "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:table)",
        )

        return bool(await self._session.value(found, { "table": self.quote(table) }))

    async def constrain ( self, blueprint: Blueprint ) -> None:

        name = self.quote(blueprint.table)

        for expression, label in blueprint.checks:

            constraint = self.quote(label or f"{blueprint.table}_check")

            await self._session.script(f"ALTER TABLE {name} ADD CONSTRAINT {constraint} CHECK ({expression})")

        for columns, label in blueprint.keys:

            constraint = self.quote(label or f"{blueprint.table}_pkey")
            listed     = ", ".join(self.quote(column) for column in columns)

            await self._session.script(f"ALTER TABLE {name} ADD CONSTRAINT {constraint} PRIMARY KEY ({listed})")

    async def release ( self, blueprint: Blueprint ) -> None:

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

    async def drop_all ( self, *tables: str ) -> int:

        for table in tables: await self.drop(table)

        return len(tables)

    async def rename ( self, old: str, new: str ) -> None:

        await self._session.script(f"ALTER TABLE {self.quote(old)} RENAME TO {self.quote(new)}")

    async def comment ( self, table: str, text: str ) -> None:

        await self._session.script(f"COMMENT ON TABLE {self.quote(table)} IS :text", { "text": text })

    async def has ( self, table: str ) -> bool:

        return await self._session.sync(lambda connection: bool(sa.inspect(connection).has_table(table)))

    async def has_column ( self, table: str, column: str ) -> bool:

        return column in await self.columns(table)

    async def has_index ( self, table: str, index: str ) -> bool:

        return index in await self.indexes(table)

    async def columns ( self, table: str ) -> list[str]:

        found = await self._session.sync(lambda connection: sa.inspect(connection).get_columns(table))

        return [str(column["name"]) for column in found]

    async def tables ( self ) -> list[str]:

        found = await self._session.sync(lambda connection: sa.inspect(connection).get_table_names())

        return sorted(str(name) for name in found)

    async def truncate ( self, table: str ) -> None:

        await self._session.truncate(table)

    async def add_column ( self, table: str, column: Column ) -> None:

        spec = str(CreateColumn(column.build()).compile(dialect=self._session.dialect()))

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
            await self.add_index(Blueprint(table), Indexed((column.name,), column.unique_))

    async def add_index ( self, blueprint: Blueprint, index: Indexed ) -> None:

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

    async def size ( self, table: str ) -> int:

        statement = sa.text("SELECT pg_total_relation_size(CAST(:table AS regclass))")

        return int(await self._session.value(statement, { "table": table }) or 0)

    def require ( self, condition: bool, reason: str ) -> None:

        if not condition: raise Fault(Code.INTERNAL, reason=reason)
