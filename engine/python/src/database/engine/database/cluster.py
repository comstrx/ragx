from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from engine.error import Code, Fault
from .engine import Database
from .schema import Schema
from .session import Adapter, Session
import sqlalchemy as sa

ROLE = """
DO $$
DECLARE
    wanted text := current_setting('provision.role');
    secret text := current_setting('provision.secret');
    verb   text := CASE WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = wanted) THEN 'ALTER' ELSE 'CREATE' END;
BEGIN
    EXECUTE format(
        '%s ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOREPLICATION PASSWORD %L',
        verb, wanted, secret
    );
END
$$
"""
BYPASS = (
    "SELECT rolsuper OR rolbypassrls FROM pg_roles "
    "WHERE rolname = COALESCE(CAST(:name AS text), CAST(current_user AS text))"
)

@dataclass(frozen=True, slots=True, kw_only=True)
class Provision:

    host        : str
    port        : int
    admin       : str
    password    : str
    maintenance : str = "postgres"
    role        : str
    secret      : str
    database    : str
    extensions  : tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class Provisioned:

    role     : str
    created  : bool
    database : str
    made     : bool
    bypasses : bool

class Cluster:

    def __init__ ( self, session: Session ) -> None:

        self._session = session

    def quote ( self, name: str ) -> str:

        return self._session.dialect().identifier_preparer.quote(name)

    async def has_role ( self, name: str ) -> bool:

        found = sa.text("SELECT 1 FROM pg_roles WHERE rolname = :name")

        return await self._session.value(found, { "name": name }) is not None

    async def role ( self, name: str, secret: str ) -> bool:

        if not self._session.in_transaction(): raise Fault(Code.INTERNAL, reason="database.cluster.transaction")
        if not secret: raise Fault(Code.INTERNAL, reason="database.cluster.secret")

        created = not await self.has_role(name)

        await self._session.bind({ "provision.role": name, "provision.secret": secret })
        await self._session.script(ROLE)

        return created

    async def drop_role ( self, name: str ) -> bool:

        if not await self.has_role(name): return False

        await self._session.script(f"DROP ROLE {self.quote(name)}")

        return True

    async def has_database ( self, name: str ) -> bool:

        found = sa.text("SELECT 1 FROM pg_database WHERE datname = :name")

        return await self._session.value(found, { "name": name }) is not None

    async def database ( self, name: str, owner: str ) -> bool:

        created        = not await self.has_database(name)
        quoted, holder = self.quote(name), self.quote(owner)

        if created: await self._session.script(f"CREATE DATABASE {quoted} OWNER {holder}")
        else: await self._session.script(f"ALTER DATABASE {quoted} OWNER TO {holder}")

        await self._session.script(f"REVOKE ALL ON DATABASE {quoted} FROM PUBLIC")

        return created

    async def connectable ( self, name: str, role: str ) -> bool:

        found = sa.text("SELECT has_database_privilege(:role, :name, 'CONNECT')")

        return bool(await self._session.value(found, { "role": role, "name": name }))

    async def drop_database ( self, name: str ) -> bool:

        if not await self.has_database(name): return False

        await self._session.script(f"DROP DATABASE {self.quote(name)} WITH (FORCE)")

        return True

    async def owner ( self, name: str ) -> str | None:

        found = sa.text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = :name")
        value = await self._session.value(found, { "name": name })

        return str(value) if value is not None else None

    async def bypasses ( self, name: str | None = None ) -> bool:

        return bool(await self._session.value(sa.text(BYPASS), { "name": name }))

    @staticmethod
    async def provision (
        adapter: Adapter, plan: Provision, options: Mapping[str, Any] | None = None, wait: float = 5.0,
    ) -> Provisioned:

        admin, target = Database(), Database()

        def url ( name: str ) -> str:

            return adapter.url(plan.host, plan.port, name, plan.admin, plan.password)

        try:

            await admin.connect(adapter, url(plan.maintenance), 1, 1, wait, options)

            async with admin.transaction() as session: created = await Cluster(session).role(plan.role, plan.secret)
            async with admin.session() as session: made = await Cluster(session).database(plan.database, plan.role)

            await target.connect(adapter, url(plan.database), 1, 1, wait, options)

            async with target.transaction() as session:
                for name in plan.extensions: await Schema(session).extension(name)

            async with admin.session() as session: bypasses = await Cluster(session).bypasses(plan.role)

        finally:

            await admin.close()
            await target.close()

        return Provisioned(plan.role, created, plan.database, made, bypasses)
