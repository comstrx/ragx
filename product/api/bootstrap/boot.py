from collections.abc import AsyncGenerator, Awaitable, Callable, MutableMapping, Sequence
from contextlib import asynccontextmanager

from engine.broadcast import broadcast
from engine.cache import cache
from engine.database import Cluster, Database, Migrator, Seeds, Status, adapters, outbox
from engine.event import events
from engine.llm import llm
from engine.queue import queue
from engine.schedule import schedule
from engine.socket import socket
from engine.fs import Path
from engine.http import App, warm
from engine.log import log
from engine.thread import thread
from config import DatabaseConfig, QueueConfig
from database.seeders import seeders

class Boot:

    def __init__ (
        self, source: Path, database: Database, settings: DatabaseConfig, application: str,
        jobs: QueueConfig | None = None, paths: tuple[str, ...] = ("/health",),
        primers: Sequence[Callable[[], Awaitable[object]]] = (),
    ) -> None:

        self._source      = source
        self._database    = database
        self._settings    = settings
        self._application = application
        self._jobs        = jobs or QueueConfig()
        self.paths        = paths
        self._primers     = tuple(primers)

    @asynccontextmanager
    async def lifespan ( self, app: App ) -> AsyncGenerator[None]:

        with log.span("boot") as facts: await self.start(app, facts)

        try: yield
        finally: await self.stop()

    async def start ( self, app: App, facts: MutableMapping[str, object] ) -> None:

        await thread.gather(self.ready(), self.schema(app), self.prime())

        facts["warmed"] = await self.warm(app)
        facts["pool"]   = self._database.describe()
        facts["queue"]  = self.work()
        facts["tasks"]  = self.clock()
        facts["events"] = events.bus().name

        if self._jobs.workers > 0: events.start()
        if self._jobs.workers > 0: outbox.start()
        if broadcast.ready(): await broadcast.start()

    async def ready ( self ) -> None:

        with log.span("boot.database"):

            await self.connect()
            await self.guard()

            if self._settings.migrate: await self.migrate()
            if self._settings.seed: await self.seed()

            await self._database.fill(self._settings.pool_min)

    async def connect ( self ) -> None:

        cfg     = self._settings
        adapter = adapters.resolve(cfg.driver)
        url     = adapter.url(cfg.host, cfg.port, cfg.database, cfg.username, cfg.password)
        options = adapter.options(cfg.sslmode, cfg.search_path, self._application)

        await self._database.connect(adapter, url, cfg.pool_min, cfg.pool_max, cfg.timeout, options)

    async def guard ( self ) -> bool:

        async with self._database.session() as session: bypasses = await Cluster(session).bypasses()

        if bypasses: log.warning("database.bypasses_isolation", role=self._settings.username)

        return bypasses

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

    async def prime ( self ) -> int:

        with log.span("boot.prime") as facts:

            await thread.gather(*(primer() for primer in self._primers))

            facts["primed"] = len(self._primers)

        return len(self._primers)

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

        if self._jobs.schedule: schedule.start(self._jobs.tick)

        return len(schedule.tasks())

    async def stop ( self ) -> None:

        with log.span("shutdown"):

            await schedule.stop()
            await socket.close_all()
            await broadcast.stop()
            await events.stop()
            await outbox.stop()
            await queue.close()
            await llm.close()
            await cache.close()
            await self._database.close()
