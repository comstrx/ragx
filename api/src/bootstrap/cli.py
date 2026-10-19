from collections.abc import Awaitable, Callable
from typing import Any

from core.broadcast import broadcast
from core.cache import cache
from core.cli import Cli, Command
from core.config import config, env
from core.database import database
from core.error import Code, Fault
from core.event import events
from core.json import json
from core.llm import llm
from core.log import log
from core.queue import queue
from core.schedule import schedule
from core.thread import thread
from .app import Application
from .boot import Boot
from .serve import Serve

type Step = Callable[[Boot], Awaitable[Any]]

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

    def __init__ ( self ) -> None:

        self._cli: Cli | None = None

    def cli ( self ) -> Cli:

        if self._cli is None: self._cli = self.build()

        return self._cli

    def build ( self ) -> Cli:

        return Cli("python -m bootstrap", "The RagX api", Application().settings().version, default="serve").add(
            Command("serve", self.serve, "Serve the api over http", "server"),
            Command("check", self.check, "Boot the full lifespan once and exit", "server"),
            Command("runbook", self.runbook, "Print routes, queues, schedule, events and redacted config", "server"),
            Command("work", self.work, "Run the queue workers and the event consumer", "workers"),
            Command("schedule", self.schedule, "Run the scheduler without workers", "workers"),
            Command("migrate", self.migrate, "Apply pending migrations", "database"),
            Command("rollback", self.rollback, "Roll back the latest migration batches", "database")
                .argument("steps", int, 1, "batches to undo")
                .flag("force", "allow it in production")
                .example("python -m bootstrap rollback 2", "python -m bootstrap rollback --force"),
            Command("status", self.status, "Show applied and pending migrations", "database"),
            Command("seed", self.seed, "Run the seeders (idempotent)", "database"),
        )

    def run ( self, args: list[str] | None = None ) -> int:

        return self.cli().run(args)

    def serve ( self ) -> int:

        Serve().run()

        return 0

    def application ( self ) -> Application:

        application = Application()
        logging     = application.logging()

        log.setup(logging.level, logging.renderer, application.logfile())

        return application

    async def check ( self ) -> int:

        application = self.application()
        app         = application.create()

        async with application.boot().lifespan(app): log.info("check.passed")

        return 0

    async def work ( self ) -> int:

        env.set("SCHEDULE_ENABLED", "false")

        return await self.forever("work")

    async def schedule ( self ) -> int:

        env.set("QUEUE_WORKERS", "0")

        return await self.forever("schedule")

    async def forever ( self, role: str ) -> int:

        application = self.application()
        app         = application.create()

        async with application.boot().lifespan(app):

            log.info(f"{role}.started")

            await thread.forever()

        return 0

    async def migrate ( self ) -> int:

        return await self.database("migrate", lambda boot: boot.migrate())

    async def rollback ( self, steps: int, force: bool ) -> int:

        if Application().settings().env.is_production() and not force:
            raise Fault(Code.FORBIDDEN, "Rolling back in production needs --force", "rollback.force")

        return await self.database("rollback", lambda boot: boot.rollback(steps))

    async def status ( self ) -> int:

        return await self.database("status", lambda boot: boot.status())

    async def seed ( self ) -> int:

        return await self.database("seed", lambda boot: boot.seed())

    async def database ( self, name: str, step: Step ) -> int:

        boot = self.application().boot()

        try:

            await boot.connect()

            with log.span(f"command.{name}") as facts: facts["done"] = await step(boot)

        finally: await database.close()

        return 0

    def runbook ( self ) -> int:

        application = self.application()
        app         = application.create()
        facts       = {
            "routes"    : app.router().describe(),
            "channels"  : broadcast.channels(),
            "schedule"  : schedule.status(),
            "queues"    : list(application.queues_config().queues),
            "handlers"  : queue.names(),
            "events"    : events.describe(),
            "cache"     : cache.describe(),
            "llm"       : llm.describe(),
            "commands"  : self.cli().describe()["commands"],
            "config"    : { name: redacted(config.get(name).describe()) for name in config.names() },
            "openapi"   : len(app.openapi().get("paths", {})),
        }

        return self.cli().say(json.pretty(facts))
