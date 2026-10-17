from collections.abc import Mapping
from uuid import UUID

from core.array import Page, array
from core.database import Database, Where, query, rows
from core.error import Code, Fault
from app.enums import Table
from app.support.dna import identity, soft_deletes, timestamps


class BaseRepository[M]:

    table : Table
    model : type[M]
    soft  : bool = True
    order : tuple[str, ...] = ("-created_at",)

    def __init__ ( self, database: Database ) -> None:

        self._database = database

    def scope ( self, where: Where | None = None ) -> dict[str, object]:
        return soft_deletes.alive(dict(where or {})) if self.soft else dict(where or {})

    async def find ( self, key: UUID | str ) -> M | None:
        return await self.find_by(id=identity.parse(key))

    async def find_by ( self, **where: object ) -> M | None:

        row = await self._database.row(query.select(self.table, where=self.scope(where), limit=1))

        return rows.into(self.model, row) if row else None

    async def one ( self, key: UUID | str ) -> M:

        found = await self.find(key)

        if found is None: raise Fault(Code.NOT_FOUND, reason=self.table)

        return found

    async def count ( self, where: Where | None = None ) -> int:

        value = await self._database.value(query.count(self.table, self.scope(where)))

        return int(value) if isinstance(value, int) else 0

    async def all ( self, page: int = 1, limit: int = 20, where: Where | None = None ) -> tuple[list[M], Page]:

        total = await self.count(where)
        meta  = array.page(total, page, limit)
        found = await self._database.fetch(query.select(
            self.table, where=self.scope(where), order=self.order,
            limit=meta["limit"], offset=array.offset(meta["page"], meta["limit"]),
        ))

        return rows.many(self.model, found), meta

    async def create ( self, values: Mapping[str, object] ) -> M:

        payload = timestamps.born({ "id": identity.new(), **values })
        row     = await self._database.row(query.insert(self.table, payload))

        if row is None: raise Fault(Code.INTERNAL, reason=self.table)

        return rows.into(self.model, row)

    async def update ( self, key: UUID | str, values: Mapping[str, object] ) -> M:

        payload = timestamps.touch(dict(values))
        row     = await self._database.row(query.update(self.table, payload, self.scope({ "id": identity.parse(key) })))

        if row is None: raise Fault(Code.NOT_FOUND, reason=self.table)

        return rows.into(self.model, row)

    async def delete ( self, key: UUID | str ) -> bool:

        where = self.scope({ "id": identity.parse(key) })

        if self.soft: return await self._database.execute(query.update(self.table, soft_deletes.mark(), where, ())) == 1

        return await self._database.execute(query.delete(self.table, where)) == 1
