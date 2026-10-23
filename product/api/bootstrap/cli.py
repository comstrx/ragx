from collections.abc import Awaitable, Callable
from typing import Any

from engine.broadcast import broadcast
from engine.cache import cache
from engine.cli import Cli, Command
from engine.config import config, env
from engine.database import Cluster, Provision, adapters, database
from engine.error import Code, Fault
from engine.event import events
from engine.json import json
from engine.llm import llm
from engine.log import log
from engine.queue import queue
from engine.schedule import schedule
from engine.test import test
from engine.thread import thread
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
            Command("check", self.check, "Boot the full lifespan twice and prove nothing leaked", "server"),
            Command("runbook", self.runbook, "Print routes, queues, schedule, events and redacted config", "server"),
            Command("work", self.work, "Run the queue workers and the event consumer", "workers"),
            Command("schedule", self.schedule, "Run the scheduler without workers", "workers"),
            Command("provision", self.provision, "Create the runtime role, its database and extensions", "database"),
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

        first, second = [await self.cycle() for _ in range(2)]
        changed       = [name for name, size in first.items() if second.get(name) != size]
        leaked        = { name: [f"{first[name]} -> {second.get(name)}"] for name in changed }

        if leaked: raise Fault(Code.INTERNAL, reason="check.leaked", errors=leaked)

        log.info("check.passed", footprint=len(first), tasks=first["tasks"])

        return 0

    async def cycle ( self ) -> dict[str, int]:

        application = self.application()
        app         = application.create()

        async with application.boot().lifespan(app): pass

        return test.footprint()

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

    async def provision ( self ) -> int:

        settings = self.application().database()
        adapter  = adapters.resolve(settings.driver)
        options  = adapter.options(settings.sslmode, settings.search_path, "provision")
        plan     = Provision(
            host=settings.host, port=settings.port, admin=settings.admin_username, password=settings.admin_password,
            maintenance=settings.admin_database, role=settings.username, secret=settings.password,
            database=settings.database, extensions=tuple(settings.extensions),
        )
        done     = await Cluster.provision(adapter, plan, options, settings.timeout)

        log.info(
            "provision.done", role=done.role, created=done.created, database=done.database, made=done.made,
            extensions=settings.extensions, bypasses=done.bypasses,
        )

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
