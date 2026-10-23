from typing import override

from engine.http import App, Group, Route
from engine.test import Bench
from bootstrap import application
import asyncio

class BootBench(Bench):

    @override
    def build ( self, *routes: Route | Group ) -> App:

        app = application()

        if routes: app.route(*routes)

        return app

    @override
    async def prepare ( self ) -> None: ...

    async def run ( self ) -> None:

        self.quiet()

        await self.cycles(8, (60.0, 400.0, 50.0))
        await self.burst("/health", 8, 150.0)

if __name__ == "__main__":

    asyncio.run(BootBench().run())
