from pathlib import Path

from core.date import date
from core.log import log
from .database import Database
from .query import Statement

LOCK = 7_201_441


class Migrator:

    table = "schema_migrations"

    def __init__ ( self, database: Database, folder: Path ) -> None:

        self._database = database
        self._folder   = folder

    def files ( self ) -> list[Path]:
        return sorted(path for path in self._folder.glob("*.sql") if path.is_file())

    async def applied ( self ) -> set[str]:

        async with self._database.session() as session:

            await session.script(self._schema_())

            rows = await session.fetch(Statement(f'SELECT "name" FROM "{self.table}"'))

        return { str(row["name"]) for row in rows }

    async def pending ( self ) -> list[Path]:

        done = await self.applied()

        return [path for path in self.files() if path.name not in done]

    async def apply ( self ) -> list[str]:

        applied: list[str] = []

        async with self._database.transaction() as session:

            await session.execute(Statement("SELECT pg_advisory_xact_lock($1)", (LOCK,)))
            await session.script(self._schema_())

            done = { str(row["name"]) for row in await session.fetch(Statement(f'SELECT "name" FROM "{self.table}"')) }

            for path in self.files():

                if path.name in done: continue

                started = date.tick()

                await session.script(path.read_text(encoding="utf-8"))
                await session.execute(Statement(f'INSERT INTO "{self.table}" ("name") VALUES ($1)', (path.name,)))

                applied.append(path.name)
                log.info("database.migrated", migration=path.name, ms=date.elapsed(started))

        return applied

    async def status ( self ) -> dict[str, object]:

        done    = await self.applied()
        pending = [path.name for path in self.files() if path.name not in done]

        return { "applied": sorted(done), "pending": pending }

    def _schema_ ( self ) -> str:

        return (
            f'CREATE TABLE IF NOT EXISTS "{self.table}" ('
            '"name" text PRIMARY KEY, "applied_at" timestamptz NOT NULL DEFAULT now())'
        )
