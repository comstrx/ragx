from collections.abc import Mapping
from typing import Any

from engine.date import date
from engine.error import Code, Fault
from engine.json import json
from sqlalchemy.dialects.postgresql import insert
from .blueprint import Blueprint
from .engine import Database
import sqlalchemy as sa

LIMIT = 1000

def shaped ( name: str ) -> sa.TableClause:

    return sa.table(
        name, sa.column("key", sa.String()), sa.column("data", sa.Text()), sa.column("version", sa.Integer()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

class Documents:

    def __init__ ( self, database: Database, table: str = "documents" ) -> None:

        self._database = database
        self._table    = shaped(table)
        self._writes   = 0
        self._clashes  = 0

    def setup ( self, table: str ) -> None:

        self._table = shaped(table)

    @staticmethod
    def define ( table: Blueprint ) -> None:

        table.string("key", 255).key()
        table.text("data")
        table.integer("version").default(1)
        table.timestamp("updated_at").default(sa.func.now())
        table.index(["updated_at"])

    async def read ( self, key: str ) -> tuple[dict[str, Any], int] | None:

        table = self._table
        found = await self._database.row(sa.select(table.c.data, table.c.version).where(table.c.key == key))

        if found is None: return None

        return dict(json.loads(str(found["data"]))), int(found["version"])

    async def write ( self, key: str, data: Mapping[str, Any], version: int ) -> bool:

        if version < 0: raise Fault(Code.VALIDATION, reason="documents.version")

        table = self._table
        body  = json.dumps(dict(data))
        now   = date.now()

        fresh   = insert(table).values(key=key, data=body, version=1, updated_at=now).on_conflict_do_nothing()
        swapped = sa.update(table).where(table.c.key == key, table.c.version == version).values(
            data=body, version=version + 1, updated_at=now,
        )
        chosen  = fresh.returning(table.c.key) if version == 0 else swapped.returning(table.c.key)
        written = await self._database.row(chosen) is not None

        self._writes  += written
        self._clashes += not written

        return written

    async def delete ( self, key: str ) -> bool:

        table = self._table

        return await self._database.execute(sa.delete(table).where(table.c.key == key)) > 0

    async def keys ( self, prefix: str = "", limit: int = LIMIT ) -> list[str]:

        table = self._table
        query = sa.select(table.c.key).where(table.c.key.startswith(prefix, autoescape=True)).order_by(table.c.key)

        return [str(row["key"]) for row in await self._database.fetch(query.limit(limit))]

    async def purge ( self, seconds: float ) -> int:

        table  = self._table
        before = date.add(date.now(), seconds=-seconds)

        return await self._database.execute(sa.delete(table).where(table.c.updated_at < before))

    async def count ( self ) -> int:

        found = await self._database.value(sa.select(sa.func.count()).select_from(self._table))

        return int(found or 0)

    def describe ( self ) -> dict[str, Any]:

        return { "table": self._table.name, "writes": self._writes, "clashes": self._clashes }
