from core.error import Code, Fault
from .session import Session
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
