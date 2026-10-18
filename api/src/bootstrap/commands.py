from collections.abc import Sequence

from core.broadcast import broadcast
from core.cache import cache
from core.config import config, env
from core.database import database
from core.event import events
from core.http import http
from core.llm import llm
from core.log import log
from core.json import json
from core.queue import queue
from core.schedule import schedule
from core.thread import thread
from .app import Application
from .serve import Serve

HIDDEN = {
    "password", "secret", "keys", "s3_secret", "local_key", "openai_key", "anthropic_key", "gemini_key", "deepseek_key",
}

def masked ( url: str ) -> str:

    start = url.find("://")
    end   = url.find("@", start + 3) if start >= 0 else -1
    colon = url.find(":", start + 3, end) if end > 0 else -1

    if colon < 0 or "/" in url[start + 3:end]: return url

    return f"{url[:colon + 1]}***{url[end:]}"

def redacted ( value: object ) -> object:

    if isinstance(value, str): return masked(value)
    if isinstance(value, dict): return { key: redacted(item) for key, item in value.items() }
    if isinstance(value, list): return [redacted(item) for item in value]

    return value

class Commands:

    names = ("serve", "migrate", "rollback", "status", "seed", "check", "work", "schedule", "runbook")

    def run ( self, args: Sequence[str] ) -> int:

        name  = args[0] if args else "serve"
        usage = f"usage: python -m bootstrap [{'|'.join(self.names)}]"

        if name not in self.names: raise SystemExit(usage)
        if name == "serve": return self.serve()

        return thread.run(self.perform(name, args[1:]))

    def serve ( self ) -> int:

        Serve().run()

        return 0

    async def perform ( self, name: str, rest: Sequence[str] ) -> int:

        if name == "work": env.set("SCHEDULE_ENABLED", "false")
        if name == "schedule": env.set("QUEUE_WORKERS", "0")

        application = Application()
        logging     = application.logging()

        log.setup(logging.level, logging.renderer, application.logfile())

        if name == "check": return await self.check(application)
        if name == "runbook": return self.runbook(application)
        if name in ("work", "schedule"): return await self.work(application, name)

        boot = application.boot()

        try:

            await boot.connect()

            with log.span(f"command.{name}") as facts:

                if name == "migrate": facts["done"] = await boot.migrate()
                if name == "rollback": facts["done"] = await boot.rollback(int(rest[0]) if rest else 1)
                if name == "seed": facts["done"] = await boot.seed()
                if name == "status": facts.update(await boot.status())

        finally: await database.close()

        return 0

    async def work ( self, application: Application, role: str ) -> int:

        app = application.create()

        async with application.boot().lifespan(app):

            log.info(f"{role}.started")

            await thread.forever()

        return 0

    def runbook ( self, application: Application ) -> int:

        app   = application.create()
        facts = {
            "routes"    : http.router(app).describe(),
            "channels"  : broadcast.channels(),
            "schedule"  : schedule.status(),
            "queues"    : list(application.queues_config().queues),
            "handlers"  : queue.names(),
            "events"    : events.describe(),
            "cache"     : cache.describe(),
            "llm"       : llm.describe(),
            "config"    : { name: redacted(config.get(name).model_dump(exclude=HIDDEN)) for name in config.names() },
            "openapi"   : len(app.openapi().get("paths", {})),
        }

        print(json.pretty(facts))

        return 0

    async def check ( self, application: Application ) -> int:

        app = application.create()

        async with application.boot().lifespan(app): log.info("check.passed")

        return 0
