from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path

from core.database import Database, Migrator, Seeds
from core.http import App, warm
from core.log import log
from core.thread import thread
from config import DatabaseConfig
from database.seeders import seeders


class Boot:

    paths = ("/health", "/v1/hello")

    def __init__ ( self, root: Path, database: Database, settings: DatabaseConfig ) -> None:

        self._root     = root
        self._database = database
        self._settings = settings

    @asynccontextmanager
    async def lifespan ( self, app: App ) -> AsyncIterator[None]:

        with log.span("boot") as facts: await self.start(app, facts)

        try: yield
        finally: await self.stop()

    async def start ( self, app: App, facts: MutableMapping[str, object] ) -> None:

        await thread.gather(self.ready(), self.schema(app))

        facts["warmed"] = await self.warm(app)
        facts["pool"]   = self._database.describe()

    async def ready ( self ) -> None:

        with log.span("boot.database"):

            await self.connect()

            if self._settings.migrate: await self.migrate()
            if self._settings.seed: await self.seed()

    async def connect ( self ) -> None:

        await self._database.connect(
            self._settings.url(), min_size=self._settings.pool_min, max_size=self._settings.pool_max,
            wait=self._settings.timeout, search_path=self._settings.search_path,
        )

    async def migrate ( self ) -> list[str]:
        return await Migrator(self._database, self._root / "database" / "migrations").apply()

    async def seed ( self ) -> list[str]:
        return await Seeds(self._database, seeders).run()

    async def schema ( self, app: App ) -> None:

        with log.span("boot.schema"): await thread.offload(app.openapi)

    async def warm ( self, app: App ) -> dict[str, int]:

        with log.span("boot.warm") as facts:

            statuses = await warm.paths(app, self.paths)

            facts.update(statuses)

        return statuses

    async def stop ( self ) -> None:

        with log.span("shutdown"): await self._database.close()
