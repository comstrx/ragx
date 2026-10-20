from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from statistics import quantiles

from core.http import Group, Route
from core.log import log
from core.test import Client, test
from bootstrap import application
import asyncio, os, time

type Work = Callable[[], Awaitable[object]]
type Measured = tuple[list[float], float]

PERCENTILES = (50, 95, 99)
SCALE       = float(os.environ.get("BENCH_SCALE", "1"))
REPEATS     = max(int(os.environ.get("BENCH_REPEATS", "3")), 1)

class Bench:

    def quiet ( self ) -> None:

        log.setup(os.environ.get("LOG_LEVEL", "warning"))

    def budget ( self, label: str, fallback: float ) -> float:

        return float(os.environ.get(f"BENCH_{label.upper()}_P99_MS", fallback)) * SCALE

    @asynccontextmanager
    async def client ( self, *routes: Route | Group ) -> AsyncGenerator[Client]:

        app = application()

        if routes: app.route(*routes)

        async with test.client(app, "http://bench", lifespan=True) as client: yield client

    async def boot ( self ) -> tuple[float, float, float]:

        started = time.perf_counter()
        app     = application()
        built   = time.perf_counter()
        span    = app.lifespan()

        await span.__aenter__()

        ready = time.perf_counter()

        await span.__aexit__(None, None, None)

        done = time.perf_counter()

        return (built - started) * 1000, (ready - built) * 1000, (done - ready) * 1000

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

    def measure_sync (
        self, work: Callable[[], object], rounds: int, clock: Callable[[], float] = time.thread_time,
    ) -> tuple[list[float], float]:

        latencies : list[float] = []
        started   = clock()

        for _ in range(rounds):

            tick = clock()

            work()

            latencies.append((clock() - tick) * 1000)

        return latencies, clock() - started

    def report (
        self, label: str, latencies: list[float], elapsed: float, p99_budget: float, attempt: int = 1,
    ) -> None:

        p50, p95, p99 = self.percentiles(latencies)
        budget        = self.budget(label, p99_budget)
        rate          = len(latencies) / elapsed if elapsed else 0.0
        timings       = f"p50 {p50:8.3f} ms · p95 {p95:8.3f} ms · p99 {p99:8.3f} ms"
        over          = f"{label}: p99 {p99:.3f} ms exceeds budget {budget:.3f} ms in {attempt} runs"
        again         = f" · run {attempt}" if attempt > 1 else ""

        print(f"{label:<14} {len(latencies):>6} ops · {rate:>9,.0f}/s · {timings}{again}")

        if p99 > budget: raise SystemExit(over)

    def percentiles ( self, latencies: list[float] ) -> tuple[float, float, float]:

        p50, p95, p99 = (quantiles(latencies, n=100)[mark - 1] for mark in PERCENTILES)

        return p50, p95, p99

    def settle ( self, label: str, run: Callable[[], Measured], p99_budget: float ) -> None:

        budget  = self.budget(label, p99_budget)
        attempt = 1
        latencies, elapsed = run()

        while self.percentiles(latencies)[2] > budget and attempt < REPEATS:

            attempt += 1
            latencies, elapsed = run()

        self.report(label, latencies, elapsed, p99_budget, attempt)

    async def asettle ( self, label: str, run: Callable[[], Awaitable[Measured]], p99_budget: float ) -> None:

        budget  = self.budget(label, p99_budget)
        attempt = 1
        latencies, elapsed = await run()

        while self.percentiles(latencies)[2] > budget and attempt < REPEATS:

            attempt += 1
            latencies, elapsed = await run()

        self.report(label, latencies, elapsed, p99_budget, attempt)

    def within ( self, label: str, spent: float, fallback: float ) -> None:

        budget = self.budget(label, fallback)
        over   = f"{label}: {spent:.2f} ms exceeds budget {budget:.2f} ms"

        if spent > budget: raise SystemExit(over)

    def expect ( self, label: str, actual: int, wanted: int, body: str = "" ) -> None:

        unexpected = f"{label}: expected {wanted}, got {actual} {body[:200]}"

        if actual != wanted: raise RuntimeError(unexpected)
