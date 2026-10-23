from collections.abc import Callable

from engine.array import Item, Search
from engine.database import Schema as Tables, database
from engine.rag import Passage, PostgresIndex, Row
from engine.rand import rand
from engine.string import string
from engine.test import Bench, Measured
import asyncio, random, time

DIMENSION = 1024
RECORDS   = 1000
QUERIES   = 100
HNSW      = 5000
WORDS     = (
    "refund", "delivery", "shipping", "invoice", "warranty", "support", "account", "payment", "order", "return",
    "الاسترداد", "الشحن", "الفاتورة", "الضمان", "الدعم", "الحساب", "الدفع", "الطلب", "التوصيل", "الارجاع",
)

class RagBench(Bench):

    def run ( self ) -> None:

        self.quiet()

        chance  = random.Random(7)
        texts   = [" ".join(chance.choices(WORDS, k=120)) for _ in range(RECORDS)]
        vectors = [tuple(chance.uniform(-1, 1) for _ in range(DIMENSION)) for _ in range(RECORDS)]
        items   = [Item(f"k{index}", "tenant", texts[index], vectors[index]) for index in range(RECORDS)]
        asked   = [(" ".join(chance.choices(WORDS, k=6)), vectors[chance.randrange(RECORDS)]) for _ in range(QUERIES)]
        index   = Search(capacity=RECORDS)
        started = time.perf_counter()

        index.upsert(items)

        spent = (time.perf_counter() - started) * 1000

        print(f"{'search.index':<14} {RECORDS:>6} items · {DIMENSION} dims · {spent:8.1f} ms")

        self.within("search.index", spent, 3000.0)

        cycle = iter(asked * 1000)

        for label, work, p99 in (
            ("search.dense",   lambda: index.dense(next(cycle)[1], "tenant", 8),    60.0),
            ("search.lexical", lambda: index.lexical(next(cycle)[0], "tenant", 8),  60.0),
            ("search.hybrid",  lambda: index.hybrid(*next(cycle), "tenant", 8),     120.0),
            ("string.chunks",  lambda: string.chunks(texts[0] * 8, 800, 80),         5.0),
        ):

            self.settle(label, self.repeat(work), p99)

        asyncio.run(self.durable(texts, vectors, asked))

    async def durable (
        self, texts: list[str], vectors: list[tuple[float, ...]], asked: list[tuple[str, tuple[float, ...]]],
    ) -> None:

        async with self.client():

            async with database.transaction() as session: installed = await Tables(session).extended("vector")

            if not installed:

                print(f"{'rag.postgres':<14} skipped · the pgvector extension is not installed")

                return

            for records, budget in ((1000, 50.0), (5000, 50.0)):
                await self.indexed(records, budget, texts, vectors, asked)

    async def indexed (
        self, records: int, budget: float, texts: list[str], vectors: list[tuple[float, ...]],
        asked: list[tuple[str, tuple[float, ...]]],
    ) -> None:

        name  = f"bench_rag_{rand.hex(3)}"
        index = PostgresIndex(database, name, DIMENSION)
        label = f"rag.pg.{records}"

        async with database.transaction() as session:
            await Tables(session).create(name, PostgresIndex.define(DIMENSION))

        try:

            started = time.perf_counter()

            for document in range(records // 100):

                rows = [
                    Row(Passage(f"{document}-{at}", f"d{document}", "bench", texts[at]), vectors[slot % RECORDS])
                    for at, slot in enumerate(range(document * 100, document * 100 + 100))
                ]

                await index.replace("tenant", f"d{document}", rows, "bench")

            spent = time.perf_counter() - started

            async with database.transaction() as session: await Tables(session).analyze(name)

            plan  = await index.explain("tenant", asked[0][1])
            used  = int(any("nearest" in line for line in plan))
            cycle = iter(asked * 100)

            chosen = "hnsw" if used else "exact"

            print(f"{label + '.index':<14} {records:>6} rows · {records / spent:9,.0f}/s · {chosen} plan")

            if records >= HNSW: self.expect(f"{label}.plan", used, 1, "\n".join(plan))

            async def search () -> None:

                query, vector = next(cycle)

                await index.search("tenant", query, vector, "bench", 8)

            await self.asettle(label, lambda: self.measure(search, QUERIES, 1), budget)

        finally:

            async with database.transaction() as session: await Tables(session).drop(name)

    def repeat ( self, work: Callable[[], object] ) -> Callable[[], Measured]:

        return lambda: self.measure_sync(work, QUERIES)

if __name__ == "__main__":

    RagBench().run()
