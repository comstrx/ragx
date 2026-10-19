from benches import Bench
import asyncio

class HelloBench(Bench):

    rounds      = 3000
    concurrency = 16

    async def run ( self ) -> None:

        async with self.client() as client:

            async def hello () -> None:

                reply = await client.get("/v1/hello", params={ "name": "World" })

                self.expect("hello", reply.code, 200, reply.text())

            async def health () -> None:

                reply = await client.get("/health")

                self.expect("health", reply.code, 200, reply.text())

            await hello()

            latencies, elapsed = await self.measure(hello, self.rounds, self.concurrency)

            self.report("hello", latencies, elapsed, 250.0)

            latencies, elapsed = await self.measure(health, self.rounds, self.concurrency)

            self.report("health", latencies, elapsed, 250.0)

if __name__ == "__main__":

    asyncio.run(HelloBench().run())
