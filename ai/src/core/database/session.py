from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Dialect
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import Executable
from .adapters import Adapter
from .errors import Translate

type Row = dict[str, Any]
type Statement = Executable
type Params = Mapping[str, object] | None

translate = Translate()

class Session:

    __slots__ = ("_adapter", "_connection", "_depth")

    def __init__ ( self, connection: AsyncConnection, adapter: Adapter, depth: int = 0 ) -> None:

        self._connection = connection
        self._adapter    = adapter
        self._depth      = depth

    def adapter ( self ) -> Adapter:

        return self._adapter

    def dialect ( self ) -> Dialect:

        return self._connection.dialect

    def connection ( self ) -> AsyncConnection:

        return self._connection

    def depth ( self ) -> int:

        return self._depth

    def deeper ( self ) -> Session:

        return Session(self._connection, self._adapter, self._depth + 1)

    def in_transaction ( self ) -> bool:

        return self._connection.in_transaction()

    async def fetch ( self, statement: Statement, params: Params = None ) -> list[Row]:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return [dict(mapping) for mapping in result.mappings().all()]

    async def row ( self, statement: Statement, params: Params = None ) -> Row | None:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        mapping = result.mappings().first()

        return dict(mapping) if mapping is not None else None

    async def value ( self, statement: Statement, params: Params = None ) -> Any:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return result.scalar()

    async def execute ( self, statement: Statement, params: Params = None ) -> int:

        try: result = await self._connection.execute(statement, params)
        except Exception as error: raise translate.fault(error) from error

        return max(result.rowcount, 0)

    async def script ( self, sql: str, params: Params = None ) -> None:

        try: await self._connection.execute(text(sql), params)
        except Exception as error: raise translate.fault(error) from error

    async def sync[T] ( self, work: Callable[[Any], T] ) -> T:

        try: return await self._connection.run_sync(work)
        except Exception as error: raise translate.fault(error) from error

    async def lock ( self, key: int ) -> None:

        await self.script(self._adapter.lock(key))

    async def truncate ( self, table: str ) -> None:

        await self.script(self._adapter.truncate(table))
