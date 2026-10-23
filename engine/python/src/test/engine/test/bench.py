from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from statistics import quantiles

from engine.error import Code, Fault
from engine.http import App, Group, Route
from engine.log import log
from .client import Answer, Client
from .stage import Stage
import asyncio, os, time

type Work = Callable[[], Awaitable[object]]
type Measured = tuple[list[float], float]

PERCENTILES = (50, 95, 99)
OK          = 200
SCALE       = float(os.environ.get("BENCH_SCALE", "1"))
REPEATS     = max(int(os.environ.get("BENCH_REPEATS", "3")), 1)

class Bench:

    def quiet ( self ) -> None:

        log.setup(os.environ.get("LOG_LEVEL", "warning"))

    def budget ( self, label: str, fallback: float ) -> float:

        return float(os.environ.get(f"BENCH_{label.upper()}_P99_MS", fallback)) * SCALE

    def build ( self, *routes: Route | Group ) -> App:

        return Stage().application(*routes)

    async def prepare ( self ) -> None:

        await Stage().provision()

    @asynccontextmanager
    async def client ( self, *routes: Route | Group ) -> AsyncGenerator[Client]:

        await self.prepare()

        app = self.build(*routes)

        async with Client(app, "http://bench", ("127.0.0.1", 50000), lifespan=True) as client: yield client

    async def boot ( self ) -> tuple[float, float, float]:

        await self.prepare()

        started = time.perf_counter()
        app     = self.build()
        built   = time.perf_counter()
        span    = app.lifespan()

        await span.__aenter__()

        ready = time.perf_counter()

        await span.__aexit__(None, None, None)

        done = time.perf_counter()

        return (built - started) * 1000, (ready - built) * 1000, (done - ready) * 1000

    async def cycles ( self, rounds: int, budgets: tuple[float, float, float] ) -> None:

        spent = [await self.boot() for _ in range(rounds)]

        for index, label in enumerate(("boot.create", "boot.ready", "boot.shutdown")):

            spans  = sorted(cycle[index] for cycle in spent[1:])
            median = spans[len(spans) // 2]
            shape  = f"best {spans[0]:8.2f} ms · median {median:8.2f} ms · worst {spans[-1]:8.2f} ms"

            print(f"{label:<14} {len(spans):>6} runs · {shape}")

            self.within(label, spans[-1], budgets[index])

    async def burst ( self, path: str, hits: int, budget: float ) -> None:

        async with self.client() as client:

            async def first () -> tuple[float, Answer]:

                started = time.perf_counter()
                answer  = await client.get(path)

                return (time.perf_counter() - started) * 1000, answer

            found = await asyncio.gather(*(first() for _ in range(hits)))

        slowest = max(spent for spent, _ in found)

        print(f"{'first.burst':<14} {len(found):>6} hits · slowest {slowest:8.2f} ms right after boot")

        self.expect("first.burst", sum(answer.code == OK for _, answer in found), len(found))
        self.within("first.burst", slowest, budget)

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

        if p99 > budget: raise Fault(Code.INTERNAL, over, "bench.budget")

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

        if spent > budget: raise Fault(Code.INTERNAL, over, "bench.budget")

    def expect ( self, label: str, actual: int, wanted: int, body: str = "" ) -> None:

        unexpected = f"{label}: expected {wanted}, got {actual} {body[:200]}"

        if actual != wanted: raise Fault(Code.INTERNAL, unexpected, "bench.status")
