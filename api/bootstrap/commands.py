from collections.abc import Sequence

from core.database import database
from core.log import log
from core.thread import thread
from .app import Application
from .serve import Serve


class Commands:

    names = ("serve", "migrate", "seed", "check")

    def run ( self, args: Sequence[str] ) -> int:

        name = args[0] if args else "serve"

        usage = f"usage: python -m bootstrap [{'|'.join(self.names)}]"

        if name not in self.names: raise SystemExit(usage)
        if name == "serve": return self.serve()

        return thread.run(self.perform(name))

    def serve ( self ) -> int:

        Serve().run()

        return 0

    async def perform ( self, name: str ) -> int:

        application = Application()
        logging     = application.logging()
        boot        = application.boot()

        log.setup(level=logging.level, renderer=logging.renderer)

        try:

            if name == "check": await self.check(application)
            else:

                await boot.connect()

                with log.span(f"command.{name}") as facts:
                    facts["done"] = await boot.migrate() if name == "migrate" else await boot.seed()

        finally: await database.close()

        return 0

    async def check ( self, application: Application ) -> None:

        app = application.create()

        async with application.boot().lifespan(app): log.info("check.passed")
