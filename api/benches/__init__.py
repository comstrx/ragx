from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from statistics import quantiles

from httpx import ASGITransport, AsyncClient
from core.log import log
from bootstrap import application
import asyncio, os, time

type Work = Callable[[], Awaitable[object]]

PERCENTILES = (50, 95, 99)
SCALE       = float(os.environ.get("BENCH_SCALE", "1"))

class Bench:

    def quiet ( self ) -> None:
        log.setup(os.environ.get("LOG_LEVEL", "warning"))

    def budget ( self, label: str, fallback: float ) -> float:
        return float(os.environ.get(f"BENCH_{label.upper()}_P99_MS", fallback)) * SCALE

    @asynccontextmanager
    async def client ( self ) -> AsyncGenerator[AsyncClient]:

        app = application()

        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://bench") as client,
        ):
            yield client

    async def measure ( self, work: Work, rounds: int, concurrency: int ) -> tuple[list[float], float]:

        gate      = asyncio.Semaphore(concurrency)
        latencies : list[float] = []

        async def one () -> None:

            async with gate:

                started = time.perf_counter()

                await work()

                latencies.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()

        async with asyncio.TaskGroup() as group:
            for _ in range(rounds): group.create_task(one())

        return latencies, time.perf_counter() - started

    def measure_sync ( self, work: Callable[[], object], rounds: int ) -> tuple[list[float], float]:

        latencies : list[float] = []
        started   = time.perf_counter()

        for _ in range(rounds):

            tick = time.perf_counter()

            work()

            latencies.append((time.perf_counter() - tick) * 1000)

        return latencies, time.perf_counter() - started

    def report ( self, label: str, latencies: list[float], elapsed: float, p99_budget: float ) -> None:

        p50, p95, p99 = (quantiles(latencies, n=100)[mark - 1] for mark in PERCENTILES)
        budget        = self.budget(label, p99_budget)
        rate          = len(latencies) / elapsed if elapsed else 0.0
        timings       = f"p50 {p50:8.3f} ms · p95 {p95:8.3f} ms · p99 {p99:8.3f} ms"
        over          = f"{label}: p99 {p99:.3f} ms exceeds budget {budget:.3f} ms"

        print(f"{label:<14} {len(latencies):>6} ops · {rate:>9,.0f}/s · {timings}")

        if p99 > budget: raise SystemExit(over)

    def expect ( self, label: str, actual: int, wanted: int, body: str = "" ) -> None:

        unexpected = f"{label}: expected {wanted}, got {actual} {body[:200]}"

        if actual != wanted: raise RuntimeError(unexpected)
