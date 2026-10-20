from core.cache import cache
from core.database import Database
from core.error import Code, Fault
from core.event import events
from core.health import Result, health
from core.http import Facts, Request, Response, Route
from core.llm import llm
from core.queue import queue
from core.storage import storage

class Heartbeat:

    def __init__ ( self, database: Database ) -> None:

        self._database = database

    def register ( self ) -> int:

        health.register("database", self.database, tags=("ready", "live"))
        health.register("cache", self.cache, critical=False, tags=("ready",))
        health.register("queue", self.queue, critical=False, tags=("ready",))
        health.register("events", lambda: Result.ok(**events.describe()), critical=False)
        health.register("storage", lambda: Result.ok(**storage.describe()), critical=False)
        health.register("llm", lambda: Result.ok(**llm.describe()), critical=False)

        return len(health.names())

    def route ( self ) -> Route:

        return Route.get("/health", self.index, name="health", tags=("health",))

    async def database ( self ) -> Result:

        alive = await self._database.ping()

        return Result.ok(alive=True, **self._database.describe()) if alive else Result.down("database", alive=False)

    async def cache ( self ) -> Result:

        pinger = getattr(cache.store(), "ping", None)
        alive  = await pinger() if callable(pinger) else True

        return Result.ok(**cache.describe()) if alive else Result.degraded("cache", **cache.describe())

    async def queue ( self ) -> Result:

        return Result.ok(**queue.describe()) if queue.ready() else Result.degraded("queue")

    async def index ( self, request: Request ) -> Response:

        facts  = Facts.of(request)
        report = await health.report()
        status = {
            "status"   : report["status"],
            "version"  : facts.get("version"),
            "release"  : facts.get("release"),
            "database" : report["checks"]["database"],
            "checks"   : report["checks"],
            "ms"       : report["ms"],
        }

        if report["checks"]["database"]["status"] != "ok":

            return Response.fail(Fault(Code.UNAVAILABLE, reason="database"), meta={ "health": status })

        return Response.ok(status)
