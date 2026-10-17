from statistics import quantiles

from httpx import ASGITransport, AsyncClient
from bootstrap import application
import asyncio, time


class HelloBench:

    requests    = 3000
    concurrency = 32
    path        = "/v1/hello"

    async def run ( self ) -> None:

        app = application()

        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://bench") as client,
        ):

            await client.get(self.path)

            gate      = asyncio.Semaphore(self.concurrency)
            latencies : list[float] = []
            started   = time.perf_counter()

            async with asyncio.TaskGroup() as group:
                for _ in range(self.requests): group.create_task(self.hit(client, gate, latencies))

            elapsed = time.perf_counter() - started

        self.report(latencies, elapsed)

    async def hit ( self, client: AsyncClient, gate: asyncio.Semaphore, latencies: list[float] ) -> None:

        async with gate:

            started  = time.perf_counter()
            response = await client.get(self.path)

            latencies.append((time.perf_counter() - started) * 1000)

            if response.status_code != 200: raise RuntimeError(response.text)

    def report ( self, latencies: list[float], elapsed: float ) -> None:

        p50, p95, p99 = (quantiles(latencies, n=100)[i - 1] for i in (50, 95, 99))

        print(f"{self.path}: {self.requests} requests, concurrency {self.concurrency}")
        print(f"rps {self.requests / elapsed:,.0f} · p50 {p50:.2f} ms · p95 {p95:.2f} ms · p99 {p99:.2f} ms")


if __name__ == "__main__": asyncio.run(HelloBench().run())
