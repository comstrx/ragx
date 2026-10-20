from core.test import Answer
from benches import Bench
import asyncio, time

class BootBench(Bench):

    rounds = 8

    async def run ( self ) -> None:

        self.quiet()

        cycles = [await self.boot() for _ in range(self.rounds)]

        for index, label, budget in ((0, "boot.create", 60.0), (1, "boot.ready", 400.0), (2, "boot.shutdown", 50.0)):

            spans  = sorted(cycle[index] for cycle in cycles[1:])
            median = spans[len(spans) // 2]

            shape  = f"best {spans[0]:8.2f} ms · median {median:8.2f} ms · worst {spans[-1]:8.2f} ms"

            print(f"{label:<14} {len(spans):>6} runs · {shape}")

            self.within(label, spans[-1], budget)

        async with self.client() as client:

            async def first ( path: str ) -> tuple[float, Answer]:

                started = time.perf_counter()
                answer  = await client.get(path)

                return (time.perf_counter() - started) * 1000, answer

            hits = await asyncio.gather(*(first("/health") for _ in range(8)))

        slowest = max(spent for spent, _ in hits)

        print(f"{'first.burst':<14} {len(hits):>6} hits · slowest {slowest:8.2f} ms right after boot")

        self.expect("first.burst", sum(answer.code == 200 for _, answer in hits), len(hits))

        self.within("first.burst", slowest, 150.0)

if __name__ == "__main__":

    asyncio.run(BootBench().run())
