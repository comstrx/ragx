from pathlib import Path

from core.database import Migrator, Statement, database
from core.http import App
import pytest

FOLDER = Path(__file__).resolve().parents[2] / "database" / "migrations"


@pytest.mark.anyio
class TestMigrator:

    async def test_every_migration_is_applied_once_and_recorded ( self, app: App ) -> None:

        migrator = Migrator(database, FOLDER)
        names    = [path.name for path in migrator.files()]

        assert names == ["0001_create_types.sql", "0002_create_users.sql"]
        assert await migrator.apply() == []
        assert await migrator.status() == { "applied": names, "pending": [] }

        kinds = await database.value(Statement("SELECT count(*) FROM pg_type WHERE typname = 'role'"))

        assert kinds == 1

    async def test_the_seed_left_the_world_in_the_users_table ( self, app: App ) -> None:

        statement = Statement('SELECT "name", "role"::text AS role FROM "users" WHERE "name" = $1', ("World",))
        row       = await database.row(statement)

        assert row == { "name": "World", "role": "client" }
