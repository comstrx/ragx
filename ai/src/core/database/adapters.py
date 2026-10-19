from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import quote

from core.error import Code, Fault

class Adapter(Protocol):

    name: str

    def url ( self, host: str, port: int, database: str, username: str, password: str ) -> str: ...

    def options ( self, sslmode: str, search_path: str, application: str ) -> dict[str, Any]: ...

    def lock ( self, key: int ) -> str: ...

    def truncate ( self, table: str ) -> str: ...

class PostgresAdapter:

    name = "postgresql"

    def url ( self, host: str, port: int, database: str, username: str, password: str ) -> str:

        auth = quote(username, safe="")
        if password: auth += ":" + quote(password, safe="")

        return f"postgresql+asyncpg://{auth}@{host}:{port}/{database}"

    def options ( self, sslmode: str, search_path: str, application: str ) -> dict[str, Any]:

        settings = { "application_name": application }
        if search_path: settings["search_path"] = search_path

        ssl: bool | None = { "disable": False, "allow": None, "prefer": None }.get(sslmode, True)

        return { "server_settings": settings, **({} if ssl is None else { "ssl": ssl }) }

    def lock ( self, key: int ) -> str:

        return f"SELECT pg_advisory_xact_lock({int(key)})"

    def truncate ( self, table: str ) -> str:

        return f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE'

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
