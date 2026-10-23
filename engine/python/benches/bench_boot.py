from engine.test import Bench
import asyncio

class BootBench(Bench):

    async def run ( self ) -> None:

        self.quiet()

        await self.cycles(8, (60.0, 400.0, 50.0))
        await self.burst("/health", 8, 150.0)

if __name__ == "__main__":

    asyncio.run(BootBench().run())
