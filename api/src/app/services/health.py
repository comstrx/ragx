from collections.abc import Mapping

from core.cache import cache
from core.database import Database
from core.event import events
from core.health import Result, health
from core.llm import llm
from core.queue import queue
from core.storage import storage
from app.utils.bases import BaseService

class HealthService(BaseService):

    def __init__ ( self, database: Database ) -> None:

        super().__init__()

        self._database = database

        health.register("database", self.database, tags=("ready", "live"))
        health.register("cache", self.cache, critical=False, tags=("ready",))
        health.register("queue", self.queue, critical=False, tags=("ready",))
        health.register("events", lambda: Result.ok(**events.describe()), critical=False)
        health.register("storage", lambda: Result.ok(**storage.describe()), critical=False)
        health.register("llm", lambda: Result.ok(**llm.describe()), critical=False)

    async def database ( self ) -> Result:

        alive = await self._database.ping()

        return Result.ok(alive=True, **self._database.describe()) if alive else Result.down("database", alive=False)

    async def cache ( self ) -> Result:

        pinger = getattr(cache.store(), "ping", None)
        alive  = await pinger() if callable(pinger) else True

        return Result.ok(**cache.describe()) if alive else Result.degraded("cache", **cache.describe())

    async def queue ( self ) -> Result:
        return Result.ok(**queue.describe()) if queue.ready() else Result.degraded("queue")

    async def status ( self, facts: Mapping[str, object] ) -> tuple[bool, dict[str, object]]:

        report = await health.report()
        alive  = report["checks"]["database"]["status"] == "ok"

        return alive, {
            "status"   : report["status"],
            "version"  : facts.get("version"),
            "release"  : facts.get("release"),
            "database" : report["checks"]["database"],
            "checks"   : report["checks"],
            "ms"       : report["ms"],
        }
