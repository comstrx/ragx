from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from asyncpg import Connection, Pool, create_pool
from asyncpg.pool import PoolConnectionProxy
from asyncpg import exceptions as pg
from core.error import Code, Fault
from core.log import log
from .errors import Translate
from .query import Statement
import asyncio, orjson

type Row = dict[str, object]
type Link = Connection[Any] | PoolConnectionProxy[Any]
type Params = tuple[object, ...]

translate = Translate()


class Session:

    def __init__ ( self, connection: Link ) -> None:

        self._connection = connection

    async def fetch ( self, statement: Statement ) -> list[Row]:

        try: return [dict(record) for record in await self._connection.fetch(statement.sql, *statement.params)]
        except Exception as error: raise translate.fault(error) from error

    async def row ( self, statement: Statement ) -> Row | None:

        try: record = await self._connection.fetchrow(statement.sql, *statement.params)
        except Exception as error: raise translate.fault(error) from error

        return dict(record) if record is not None else None

    async def value ( self, statement: Statement ) -> object:

        try: return await self._connection.fetchval(statement.sql, *statement.params)
        except Exception as error: raise translate.fault(error) from error

    async def execute ( self, statement: Statement ) -> int:

        try: status = await self._connection.execute(statement.sql, *statement.params)
        except Exception as error: raise translate.fault(error) from error

        return self._count_(status)

    async def script ( self, sql: str ) -> None:

        try: await self._connection.execute(sql)
        except Exception as error: raise translate.fault(error) from error

    def _count_ ( self, status: str ) -> int:

        tail = status.rsplit(" ", 1)[-1]

        return int(tail) if tail.isdigit() else 0


class Database:

    def __init__ ( self ) -> None:

        self._pool: Pool[Any] | None = None

    def ready ( self ) -> bool:
        return self._pool is not None

    async def connect (
        self, dsn: str, min_size: int = 1, max_size: int = 10, wait: float = 5.0,
        statements: int = 256, application: str = "api", search_path: str | None = None,
    ) -> None:

        if self._pool is not None: return

        try:

            self._pool = await create_pool(
                dsn, min_size=min_size, max_size=max_size, timeout=wait, command_timeout=wait,
                statement_cache_size=statements, server_settings=self._settings_(application, search_path),
                init=self._prepare_,
            )

        except Exception as error: raise translate.fault(error) from error

        log.info("database.connected", min=min_size, max=max_size)

    async def close ( self ) -> None:

        if self._pool is None: return

        pool, self._pool = self._pool, None

        await pool.close()
        log.info("database.closed")

    async def ping ( self, wait: float = 2.0 ) -> bool:

        if self._pool is None: return False

        try:

            async with asyncio.timeout(wait): value = await self._pool.fetchval("SELECT 1")

            return bool(value == 1)

        except (OSError, TimeoutError, pg.PostgresError, pg.InterfaceError):

            log.warning("database.unreachable")

            return False

    @asynccontextmanager
    async def session ( self ) -> AsyncIterator[Session]:

        async with self._acquire_() as connection: yield Session(connection)

    @asynccontextmanager
    async def transaction ( self ) -> AsyncIterator[Session]:

        async with self._acquire_() as connection, connection.transaction(): yield Session(connection)

    async def fetch ( self, statement: Statement ) -> list[Row]:

        async with self.session() as session: return await session.fetch(statement)

    async def row ( self, statement: Statement ) -> Row | None:

        async with self.session() as session: return await session.row(statement)

    async def value ( self, statement: Statement ) -> object:

        async with self.session() as session: return await session.value(statement)

    async def execute ( self, statement: Statement ) -> int:

        async with self.session() as session: return await session.execute(statement)

    @asynccontextmanager
    async def _acquire_ ( self ) -> AsyncIterator[Link]:

        if self._pool is None: raise Fault(Code.UNAVAILABLE, reason="database")

        try:

            async with self._pool.acquire() as connection: yield connection

        except Fault: raise
        except Exception as error: raise translate.fault(error) from error

    def _settings_ ( self, application: str, search_path: str | None ) -> dict[str, str]:

        settings = { "application_name": application }
        if search_path: settings["search_path"] = search_path

        return settings

    async def _prepare_ ( self, connection: Connection[Any] ) -> None:

        for name in ("json", "jsonb"):

            await connection.set_type_codec(
                name, schema="pg_catalog", format="text",
                encoder=lambda value: orjson.dumps(value).decode(), decoder=orjson.loads,
            )

    def describe ( self ) -> Mapping[str, object]:

        if self._pool is None: return { "ready": False }

        return {
            "ready": True,
            "size": self._pool.get_size(),
            "idle": self._pool.get_idle_size(),
            "min": self._pool.get_min_size(),
            "max": self._pool.get_max_size(),
        }
