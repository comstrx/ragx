from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Sequence
from typing import Any

from core.array import Page, array
from core.date import date
from core.error import Code, Fault
from core.rand import rand
from sqlalchemy.dialects.postgresql import insert as upsert
import sqlalchemy as sa
from .engine import Row, Session
from .filters import Filters
from .model import Model
from .relations import Loader
from .rows import Rows
from .scope import Values

type Work = Callable[[Session], Awaitable[Any]]
type Each[M] = Callable[[M], Awaitable[Any] | Any]

rows = Rows()

class Query[M: Model](Filters[M]):

    async def get ( self ) -> list[M]:

        statement = self._statement_()
        found     = rows.many(self._model, await self._fetch_(statement))

        await self._load_(found)

        return found

    async def first ( self ) -> M | None:

        found = await self.limit(1).get()

        return found[0] if found else None

    async def first_or_fail ( self ) -> M:

        found = await self.first()

        if found is None: raise Fault(Code.NOT_FOUND, reason=self._model.table)

        return found

    async def sole ( self ) -> M:

        found = await self.limit(2).get()

        if len(found) != 1: raise Fault(Code.NOT_FOUND if not found else Code.CONFLICT, reason=self._model.table)

        return found[0]

    async def find ( self, key: object ) -> M | None:
        return await self.where_key(key).first()

    async def find_or_fail ( self, key: object ) -> M:
        return await self.where_key(key).first_or_fail()

    async def find_many ( self, keys: Iterable[object] ) -> list[M]:

        wanted = list(keys)

        return await self.where_keys(wanted).get() if wanted else []

    async def count ( self ) -> int:
        return int(await self._aggregate_(sa.func.count()) or 0)

    async def exists ( self ) -> bool:
        return await self.limit(1).count() > 0

    async def missing ( self ) -> bool:
        return not await self.exists()

    async def sum ( self, column: str ) -> Any:
        return await self._aggregate_(sa.func.sum(self._table.c[column])) or 0

    async def avg ( self, column: str ) -> Any:
        return await self._aggregate_(sa.func.avg(self._table.c[column]))

    async def min ( self, column: str ) -> Any:
        return await self._aggregate_(sa.func.min(self._table.c[column]))

    async def max ( self, column: str ) -> Any:
        return await self._aggregate_(sa.func.max(self._table.c[column]))

    async def value ( self, column: str ) -> Any:

        statement = sa.select(self._table.c[column]).where(*self._where_()).order_by(*self._order_()).limit(1)
        found     = await self._fetch_(statement)

        return found[0][column] if found else None

    async def pluck ( self, column: str, key: str | None = None ) -> Any:

        picked    = [self._table.c[column]] + ([self._table.c[key]] if key else [])
        statement = sa.select(*picked).where(*self._where_()).order_by(*self._order_())

        if self._state.limit is not None: statement = statement.limit(self._state.limit)
        if self._state.offset: statement = statement.offset(self._state.offset)

        found = await self._fetch_(statement)

        if key: return { row[key]: row[column] for row in found }

        return [row[column] for row in found]

    async def paginate ( self, page: int = 1, limit: int = 20 ) -> tuple[list[M], Page]:

        meta = array.page(await self.count(), page, limit)

        return await self.limit(meta["limit"]).offset(array.offset(meta["page"], meta["limit"])).get(), meta

    async def chunk ( self, size: int = 500 ) -> AsyncIterator[list[M]]:

        offset = 0

        while True:

            batch = await self.limit(size).offset(offset).get()

            if not batch: return

            yield batch

            if len(batch) < size: return

            offset += size

    async def cursor ( self, size: int = 500 ) -> AsyncIterator[M]:

        async for batch in self.chunk(size):
            for item in batch: yield item

    async def each ( self, work: Each[M], size: int = 500 ) -> int:

        done = 0

        async for item in self.cursor(size):

            result = work(item)

            if isinstance(result, Awaitable): await result

            done += 1

        return done

    async def create ( self, values: Values ) -> M:

        payload   = self._stamp_(dict(values), creating=True)
        statement = sa.insert(self._table).values(**payload).returning(*self._table.c)
        row       = await self._run_(lambda session: session.row(statement))

        if row is None: raise Fault(Code.INTERNAL, reason=self._model.table)

        return rows.into(self._model, row)

    async def insert ( self, items: Sequence[Values] ) -> int:

        if not items: return 0

        payloads = [self._stamp_(dict(values), creating=True) for values in items]

        return int(await self._run_(lambda session: session.execute(sa.insert(self._table).values(payloads))))

    async def upsert ( self, items: Sequence[Values], conflict: Sequence[str], update: Sequence[str] = () ) -> int:

        if not items: return 0

        payloads  = [self._stamp_(dict(values), creating=True) for values in items]
        statement = upsert(self._table).values(payloads)
        changing  = list(update) or [name for name in payloads[0] if name not in conflict]
        merged    = statement.on_conflict_do_update(
            index_elements=list(conflict), set_={ name: statement.excluded[name] for name in changing },
        )

        return int(await self._run_(lambda session: session.execute(merged)))

    async def update ( self, values: Values ) -> int:

        payload   = self._stamp_(dict(values), creating=False)
        statement = sa.update(self._table).where(*self._where_()).values(**payload)

        return int(await self._run_(lambda session: session.execute(statement)))

    async def touch ( self, column: str = "updated_at" ) -> int:
        return await self.update({ column: date.now() })

    async def first_or_create ( self, where: Values, values: Values | None = None ) -> M:

        found = await self.scoped(where).first()

        return found if found is not None else await self.create({ **where, **(values or {}) })

    async def update_or_create ( self, where: Values, values: Values ) -> M:

        found = await self.scoped(where).first()

        if found is None: return await self.create({ **where, **values })

        await self.where_key(found.key()).update(values)

        return await self.find_or_fail(found.key())

    async def increment ( self, column: str, step: int = 1, extra: Values | None = None ) -> int:

        payload   = self._stamp_(dict(extra or {}), creating=False)
        statement = sa.update(self._table).where(*self._where_()).values(
            { self._table.c[column]: self._table.c[column] + step, **payload },
        )

        return int(await self._run_(lambda session: session.execute(statement)))

    async def decrement ( self, column: str, step: int = 1, extra: Values | None = None ) -> int:
        return await self.increment(column, -step, extra)

    async def delete ( self ) -> int:

        if self._model.soft and self._state.trash == "alive": return await self.update({ "deleted_at": date.now() })

        statement = sa.delete(self._table).where(*self._where_())

        return int(await self._run_(lambda session: session.execute(statement)))

    async def destroy ( self, *keys: object ) -> int:
        return await self.where_keys(keys).delete() if keys else 0

    async def force_delete ( self ) -> int:

        statement = sa.delete(self._table).where(*self._where_(trash="all"))

        return int(await self._run_(lambda session: session.execute(statement)))

    async def restore ( self ) -> int:

        statement = sa.update(self._table).where(*self._where_(trash="trashed")).values(deleted_at=None)

        return int(await self._run_(lambda session: session.execute(statement)))

    async def truncate ( self ) -> None:
        await self._run_(lambda session: session.truncate(self._model.table))

    def _stamp_ ( self, values: dict[str, object], creating: bool ) -> dict[str, object]:

        columns = self._model.columns()
        primary = self._model.primary
        now     = date.now()

        if creating and primary in columns and values.get(primary) is None: values[primary] = rand.uuid()
        if self._model.timestamps and "updated_at" in columns: values.setdefault("updated_at", now)
        if creating and self._model.timestamps and "created_at" in columns: values.setdefault("created_at", now)

        return values

    async def _aggregate_ ( self, expression: Any ) -> Any:

        statement = sa.select(expression).select_from(self._table).where(*self._where_())

        return await self._run_(lambda session: session.value(statement))

    async def _run_ ( self, work: Work ) -> Any:

        if self._session is not None: return await work(self._session)

        async with self._database.session() as session: return await work(session)

    async def _fetch_ ( self, statement: Any ) -> list[Row]:

        found: list[Row] = await self._run_(lambda session: session.fetch(statement))

        return found

    def _related_ ( self, model: type[Model] ) -> Query[Any]:
        return Query(model, self._database, self._session)

    async def _load_ ( self, found: list[M] ) -> None:

        if self._state.loads: await Loader(self._model, self._related_, self._fetch_).load(found, self._state.loads)
