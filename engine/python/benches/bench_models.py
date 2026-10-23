from engine.llm import CORE, EMBED, INSTRUCT, RANK, TOKENS, Local, Message, Model, Options, Prompt, Sessions
from engine.test import Bench
import asyncio, os

LIVE      = (
    "RAG_LIVE_GENERATION_URL", "RAG_LIVE_GENERATION_MODEL", "RAG_LIVE_EMBEDDING_URL", "RAG_LIVE_EMBEDDING_MODEL",
    "RAG_LIVE_RANKING_URL", "RAG_LIVE_RANKING_MODEL",
)
QUESTION  = "How many days do I have to request a refund for a damaged order?"
DOCUMENTS = tuple(
    f"Policy {index}: refunds are accepted within {index + 10} days when the order arrives damaged or late."
    for index in range(10)
)

class ModelBench(Bench):

    def run ( self ) -> None:

        self.quiet()

        found = [os.environ.get(name, "") for name in LIVE]

        if not all(found):

            print(f"models: skipped, set {' '.join(LIVE)} to measure a live model stack")

            return

        asyncio.run(self.live(*found))

    def local ( self, model: str, url: str, name: str, serves: frozenset[str] ) -> Local:

        return Local(Model(model, url, name=name, serves=serves, timeout=120.0, retries=0))

    async def live ( self, *stack: str ) -> None:

        writing, written, vectoring, vectored, ranking, ranked = stack

        sessions = Sessions()
        writer   = self.local(written, writing, "writer", CORE | {TOKENS})
        vectors  = Prompt(self.local(vectored, vectoring, "vectors", frozenset({EMBED, INSTRUCT})), sessions)
        ranker   = Prompt(self.local(ranked, ranking, "ranker", frozenset({RANK})), sessions)
        answer   = Prompt(writer, sessions).temperature(0.0).max_tokens(32)
        turns    = [Message.user(QUESTION)]

        async def embed () -> None:

            await vectors.embed([QUESTION], query=True, instruction="Find the policy that answers the question")

        async def batch () -> None:

            await vectors.embed(DOCUMENTS)

        async def rank () -> None:

            await ranker.rank(QUESTION, DOCUMENTS)

        async def count () -> None:

            await writer.count(turns, Options())

        async def ask () -> None:

            await answer.ask(QUESTION)

        try:

            await self.asettle("embed.query", lambda: self.measure(embed, 40, 1), 1500.0)
            await self.asettle("embed.batch10", lambda: self.measure(batch, 20, 1), 10000.0)
            await self.asettle("rank.10", lambda: self.measure(rank, 20, 1), 10000.0)
            await self.asettle("tokens.count", lambda: self.measure(count, 40, 1), 1000.0)
            await self.asettle("generate.32", lambda: self.measure(ask, 10, 1), 30000.0)

        finally:

            for provider in (writer, vectors.provider(), ranker.provider()): await provider.close()

if __name__ == "__main__":

    ModelBench().run()
