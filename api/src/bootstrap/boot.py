from collections.abc import AsyncGenerator, MutableMapping
from contextlib import asynccontextmanager

from core.database import Database, Migrator, Seeds, Status, adapters
from core.queue import queue
from core.schedule import schedule
from core.socket import socket
from core.fs import Path
from core.http import App, warm
from core.log import log
from core.thread import thread
from config import DatabaseConfig, QueueConfig, ScheduleConfig
from database.seeders import seeders

class Boot:

    def __init__ (
        self, source: Path, database: Database, settings: DatabaseConfig, application: str,
        jobs: QueueConfig | None = None, timetable: ScheduleConfig | None = None,
        paths: tuple[str, ...] = ("/health",),
    ) -> None:

        self._source      = source
        self._database    = database
        self._settings    = settings
        self._application = application
        self._jobs        = jobs or QueueConfig()
        self._timetable   = timetable or ScheduleConfig()
        self.paths        = paths

    @asynccontextmanager
    async def lifespan ( self, app: App ) -> AsyncGenerator[None]:

        with log.span("boot") as facts: await self.start(app, facts)

        try: yield
        finally: await self.stop()

    async def start ( self, app: App, facts: MutableMapping[str, object] ) -> None:

        await thread.gather(self.ready(), self.schema(app))

        facts["warmed"] = await self.warm(app)
        facts["pool"]   = self._database.describe()
        facts["queue"]  = self.work()
        facts["tasks"]  = self.clock()

    async def ready ( self ) -> None:

        with log.span("boot.database"):

            await self.connect()

            if self._settings.migrate: await self.migrate()
            if self._settings.seed: await self.seed()

    async def connect ( self ) -> None:

        cfg     = self._settings
        adapter = adapters.resolve(cfg.driver)
        url     = adapter.url(cfg.host, cfg.port, cfg.database, cfg.username, cfg.password)
        options = adapter.options(cfg.sslmode, cfg.search_path, self._application)

        await self._database.connect(adapter, url, cfg.pool_min, cfg.pool_max, cfg.timeout, options)

    def migrator ( self ) -> Migrator:
        return Migrator(self._database, self._source / "database" / "migrations")

    async def migrate ( self ) -> list[str]:
        return await self.migrator().apply()

    async def rollback ( self, steps: int = 1 ) -> list[str]:
        return await self.migrator().rollback(steps)

    async def status ( self ) -> Status:
        return await self.migrator().status()

    async def seed ( self ) -> list[str]:
        return await Seeds(self._database, seeders).run()

    async def schema ( self, app: App ) -> None:

        with log.span("boot.schema"): await thread.offload(app.openapi)

    async def warm ( self, app: App ) -> dict[str, int]:

        with log.span("boot.warm") as facts:

            statuses = await warm.paths(app, self.paths)

            facts.update(statuses)

        return statuses

    def work ( self ) -> int:

        queue.start(self._jobs.workers)

        return len(queue.names())

    def clock ( self ) -> int:

        if self._timetable.enabled: schedule.start(self._timetable.tick)

        return len(schedule.tasks())

    async def stop ( self ) -> None:

        with log.span("shutdown"):

            await schedule.stop()
            await socket.close_all()
            await queue.stop()
            await self._database.close()
