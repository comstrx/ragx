from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any

from core.error import Code, Fault
from core.log import log
from sqlalchemy import text
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.sql import Executable
from .adapters import Adapter
from .errors import Translate
import asyncio

type Row = dict[str, Any]
type Statement = Executable

translate = Translate()

RECYCLE = 900

class Session:

    def __init__ ( self, connection: AsyncConnection, adapter: Adapter ) -> None:

        self._connection = connection
        self._adapter    = adapter

    def adapter ( self ) -> Adapter:
        return self._adapter

    def dialect ( self ) -> Dialect:
        return self._connection.dialect

    async def fetch ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> list[Row]:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return [dict(mapping) for mapping in result.mappings().all()]

    async def row ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> Row | None:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        mapping = result.mappings().first()

        return dict(mapping) if mapping is not None else None

    async def value ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> Any:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return result.scalar()

    async def execute ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> int:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0

    async def script ( self, sql: str, params: Mapping[str, object] | None = None ) -> None:

        try: await self._connection.execute(text(sql), params)
        except Exception as error: raise translate.fault(error) from error

    async def sync[T] ( self, work: Callable[[Any], T] ) -> T:

        try: return await self._connection.run_sync(work)
        except Exception as error: raise translate.fault(error) from error

    async def lock ( self, key: int ) -> None:
        await self.script(self._adapter.lock(key))

    async def truncate ( self, table: str ) -> None:
        await self.script(self._adapter.truncate(table))

class Database:

    def __init__ ( self ) -> None:

        self._engine: AsyncEngine | None = None
        self._reader: AsyncEngine | None = None
        self._adapter: Adapter | None = None

    def ready ( self ) -> bool:
        return self._engine is not None

    def adapter ( self ) -> Adapter:

        if self._adapter is None: raise Fault(Code.UNAVAILABLE, reason="database")

        return self._adapter

    def dialect ( self ) -> Dialect:

        if self._engine is None: raise Fault(Code.UNAVAILABLE, reason="database")

        return self._engine.dialect

    async def connect (
        self, adapter: Adapter, url: str, min_size: int = 1, max_size: int = 10, wait: float = 5.0,
        options: Mapping[str, Any] | None = None,
    ) -> None:

        if self._engine is not None: return

        try:

            engine = create_async_engine(
                url, pool_size=max(max_size, min_size, 1), max_overflow=0, pool_timeout=wait, pool_use_lifo=True,
                pool_recycle=RECYCLE, connect_args=dict(options or {}),
            )

            async with asyncio.timeout(wait), engine.connect() as connection: await connection.execute(text("SELECT 1"))

        except Exception as error: raise translate.fault(error) from error

        self._engine  = engine
        self._reader  = engine.execution_options(isolation_level="AUTOCOMMIT")
        self._adapter = adapter

        log.info("database.connected", driver=adapter.name, min=min_size, max=max_size)

    async def close ( self ) -> None:

        if self._engine is None: return

        engine, self._engine, self._reader = self._engine, None, None

        await engine.dispose()
        log.info("database.closed")

    async def ping ( self, wait: float = 2.0 ) -> bool:

        if self._engine is None: return False

        try:

            async with asyncio.timeout(wait), self._engine.connect() as connection:
                return (await connection.execute(text("SELECT 1"))).scalar() == 1

        except (SQLAlchemyError, OSError, TimeoutError):

            log.warning("database.unreachable")

            return False

    @asynccontextmanager
    async def session ( self ) -> AsyncGenerator[Session]:

        async with self._open_(self._reader) as connection: yield Session(connection, self.adapter())

    @asynccontextmanager
    async def transaction ( self ) -> AsyncGenerator[Session]:

        async with self._open_(self._engine) as connection, connection.begin():
            yield Session(connection, self.adapter())

    async def fetch ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> list[Row]:

        async with self.session() as session: return await session.fetch(statement, params)

    async def row ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> Row | None:

        async with self.session() as session: return await session.row(statement, params)

    async def value ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> Any:

        async with self.session() as session: return await session.value(statement, params)

    async def execute ( self, statement: Statement, params: Mapping[str, object] | None = None ) -> int:

        async with self.session() as session: return await session.execute(statement, params)

    def describe ( self ) -> Mapping[str, object]:

        if self._engine is None: return { "ready": False }

        pool = self._engine.pool

        if not isinstance(pool, QueuePool): return { "ready": True, "driver": self.adapter().name }

        return {
            "ready"   : True,
            "driver"  : self.adapter().name,
            "size"    : pool.size(),
            "idle"    : pool.checkedin(),
            "busy"    : pool.checkedout(),
            "overflow": pool.overflow(),
        }

    @asynccontextmanager
    async def _open_ ( self, engine: AsyncEngine | None ) -> AsyncGenerator[AsyncConnection]:

        if engine is None: raise Fault(Code.UNAVAILABLE, reason="database")

        try:

            async with engine.connect() as connection: yield connection

        except Fault: raise
        except Exception as error: raise translate.fault(error) from error
