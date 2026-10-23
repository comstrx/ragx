from collections.abc import AsyncIterator

from engine.config import env
from engine.database import Cluster, Database, adapters
from engine.error import Code
from engine.http import App
from engine.rand import rand
from engine.test import expect, test
import pytest

@pytest.fixture
async def admin ( app: App ) -> AsyncIterator[Database]:

    adapter = adapters.resolve(env.text("DB_DRIVER", "postgresql"))
    target  = adapter.url(
        env.text("DB_HOST", "127.0.0.1"), env.int("DB_PORT", 5432), env.text("DB_ADMIN_DATABASE", "postgres"),
        env.text("DB_ADMIN_USERNAME", "postgres"), env.text("DB_ADMIN_PASSWORD"),
    )
    found   = Database()

    await found.connect(adapter, target, 1, 1, 5.0, adapter.options("disable", "public", "cluster"))

    try: yield found
    finally: await found.close()

class TestCluster:

    async def test_provisioning_yields_a_role_that_cannot_bypass_and_a_private_base ( self, admin: Database ) -> None:

        role = f"scratch_role_{rand.hex(3)}"
        name = f"scratch_db_{rand.hex(3)}"

        try:

            async with admin.session() as session:

                await test.rejects(Cluster(session).role(role, "secret"), Code.INTERNAL, "database.cluster.transaction")

            async with admin.transaction() as session:

                await test.rejects(Cluster(session).role(role, ""), Code.INTERNAL, "database.cluster.secret")

            created = []

            for secret in ("first:secret$1", "second'secret"):

                async with admin.transaction() as session: created.append(await Cluster(session).role(role, secret))

            async with admin.session() as session:

                cluster = Cluster(session)

                made = [await cluster.database(name, role), await cluster.database(name, role)]

                expect((created, made)).equals(([True, False], [True, False]))
                expect((await cluster.owner(name), await cluster.bypasses(role), await cluster.bypasses())).equals(
                    (role, False, True),
                )
                expect((await cluster.connectable(name, role), await cluster.connectable(name, "pg_monitor"))).equals(
                    (True, False),
                )

        finally:

            async with admin.session() as session:

                cluster = Cluster(session)
                dropped = [await cluster.drop_database(name), await cluster.drop_role(role)]
                again   = [await cluster.drop_database(name), await cluster.drop_role(role)]

            expect((dropped, again)).equals(([True, True], [False, False]))
