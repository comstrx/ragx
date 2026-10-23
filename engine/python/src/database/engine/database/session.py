from collections.abc import Callable, Mapping
from typing import Any, Protocol
from urllib.parse import quote

from engine.error import Code, Fault
from sqlalchemy import text
from sqlalchemy.engine import Dialect
from sqlalchemy.exc import (
    DBAPIError, DisconnectionError, InterfaceError, OperationalError, SQLAlchemyError, TimeoutError as PoolTimeout,
)
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import Executable
import asyncio, re, time

type Row = dict[str, Any]
type Statement = Executable
type Params = Mapping[str, object] | None
CONFLICT    = ("23505",)
REFERENCE   = ("23503", "23001")
VALIDATION  = ("23502", "23514", "22")
CONNECTION  = ("08", "53", "57P")
PRIVILEGE   = "42501"
SETTING     = re.compile(r"[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*")
SERIAL      = "40001"
DEADLOCK    = "40P01"
FAILURES    = (SQLAlchemyError, OSError, TimeoutError)

def checkout ( dialect: Dialect, idle: float ) -> Callable[[Any, Any, Any], None]:

    def pinged ( connection: Any, record: Any, _proxy: Any ) -> None:

        now  = time.monotonic()
        last = record.info.get("used", now)

        record.info["used"] = now

        if now - last < idle: return

        try: dialect.do_ping(connection)
        except (dialect.loaded_dbapi.Error, *FAILURES) as error: raise DisconnectionError from error

    return pinged

class Adapter(Protocol):

    name: str

    def url ( self, host: str, port: int, database: str, username: str, password: str ) -> str: ...

    def options ( self, sslmode: str, search_path: str, application: str ) -> dict[str, Any]: ...

    def lock ( self, key: int ) -> str: ...

    def truncate ( self, table: str ) -> str: ...

    def isolate ( self, table: str, column: str, setting: str, kind: str, policy: str ) -> list[str]: ...

    def share ( self, table: str, policy: str ) -> list[str]: ...

    def bind ( self, count: int ) -> str: ...

class PostgresAdapter:

    name = "postgresql"

    def url ( self, host: str, port: int, database: str, username: str, password: str ) -> str:

        auth = quote(username, safe="")
        if password: auth += ":" + quote(password, safe="")

        return f"postgresql+asyncpg://{auth}@{host}:{port}/{database}"

    def options ( self, sslmode: str, search_path: str, application: str ) -> dict[str, Any]:

        settings = { "application_name": application, "timezone": "UTC" }
        if search_path: settings["search_path"] = search_path

        ssl: bool | None = { "disable": False, "allow": None, "prefer": None }.get(sslmode, True)

        return { "server_settings": settings, **({} if ssl is None else { "ssl": ssl }) }

    def lock ( self, key: int ) -> str:

        return f"SELECT pg_advisory_xact_lock({int(key)})"

    def truncate ( self, table: str ) -> str:

        return f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'

    def isolate ( self, table: str, column: str, setting: str, kind: str, policy: str ) -> list[str]:

        owned = f"{column} = NULLIF(current_setting('{setting}', true), '')::{kind}"

        return [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"DROP POLICY IF EXISTS {policy} ON {table}",
            f"CREATE POLICY {policy} ON {table} USING ({owned}) WITH CHECK ({owned})",
        ]

    def share ( self, table: str, policy: str ) -> list[str]:

        return [
            f"DROP POLICY IF EXISTS {policy} ON {table}", f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        ]

    def bind ( self, count: int ) -> str:

        return "SELECT " + ", ".join(f"set_config(:name{index}, :value{index}, true)" for index in range(count))

class Adapters:

    def __init__ ( self ) -> None:

        self._known: dict[str, Adapter] = { PostgresAdapter.name: PostgresAdapter() }

    def register ( self, adapter: Adapter ) -> None:

        self._known[adapter.name] = adapter

    def names ( self ) -> list[str]:

        return sorted(self._known)

    def resolve ( self, name: str ) -> Adapter:

        adapter = self._known.get(name)

        if adapter is None: raise Fault(Code.INTERNAL, reason=f"database.driver.{name}")

        return adapter

    def known ( self ) -> Mapping[str, Adapter]:

        return dict(self._known)

class Translate:

    def fault ( self, error: BaseException ) -> Fault:

        match error:
            case Fault(): return error
            case DBAPIError() if self._state_(error) in (SERIAL, DEADLOCK): return self._dbapi_(error)
            case PoolTimeout() | OperationalError() | InterfaceError():
                return Fault(Code.UNAVAILABLE, reason="database")
            case DBAPIError(): return self._dbapi_(error)
            case OSError() | asyncio.TimeoutError() | TimeoutError(): return Fault(Code.UNAVAILABLE, reason="database")
            case SQLAlchemyError(): return Fault(Code.INTERNAL, reason="database")
            case _: return Fault(Code.INTERNAL, reason="database")

    def _state_ ( self, error: DBAPIError ) -> str:

        origin = error.orig

        return str(getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None) or "")

    def _origins_ ( self, error: DBAPIError ) -> tuple[object, ...]:

        origin = error.orig

        return (origin, getattr(origin, "__cause__", None))

    def _detail_ ( self, error: DBAPIError, name: str ) -> str | None:

        for origin in self._origins_(error):

            value = getattr(origin, name, None)

            if value: return str(value)

        return None

    def _constraint_ ( self, error: DBAPIError ) -> str | None:

        for name in ("constraint_name", "column_name", "table_name"):

            value = self._detail_(error, name)

            if value: return value

        return None

    def _dbapi_ ( self, error: DBAPIError ) -> Fault:

        state = self._state_(error)
        name  = self._constraint_(error)

        if state == SERIAL: return Fault(Code.CONFLICT, reason="database.serialization")
        if state == DEADLOCK: return Fault(Code.CONFLICT, reason="database.deadlock")
        if state.startswith(CONFLICT): return Fault(Code.CONFLICT, reason=name)
        if state.startswith(REFERENCE): return Fault(Code.BAD_REQUEST, reason=name)
        if state == PRIVILEGE: return Fault(Code.FORBIDDEN, reason="database.privilege")
        if state.startswith(VALIDATION): return Fault(Code.VALIDATION, reason=name, errors=self._errors_(error))
        if state.startswith(CONNECTION) or error.connection_invalidated:
            return Fault(Code.UNAVAILABLE, reason="database")

        return Fault(Code.INTERNAL, reason="database")

    def _errors_ ( self, error: DBAPIError ) -> dict[str, list[str]] | None:

        column = self._detail_(error, "column_name")

        return { column: [Code.VALIDATION.message()] } if column else None

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

    async def bind ( self, settings: Mapping[str, str] ) -> None:

        named: dict[str, object] = {}

        for index, (name, value) in enumerate(settings.items()):
            named |= { f"name{index}": name, f"value{index}": value }

        if named: await self.script(self._adapter.bind(len(settings)), named)
