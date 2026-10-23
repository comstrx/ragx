from collections.abc import Iterable, Sequence
from dataclasses import replace

from engine.array import Metrics, Ranking
from engine.error import Code, Fault
from engine.llm import Llm, Prompt, Score
from engine.number import Embedding
from .contract import Index, Passage, Policies, Settings

PAIR = 2

class Retriever:

    def __init__ ( self, brain: Llm, policies: Policies, settings: Settings ) -> None:

        self._llm      = brain
        self._policies = policies
        self._settings = settings

    def embedder ( self, provider: str | None = None ) -> Prompt:

        chosen = self._llm.prompt(provider) if provider is not None else self._llm.task("embed")

        return chosen.harness(self._policies.stage("embedding"))

    def ranker ( self, provider: str | None = None ) -> Prompt | None:

        if provider is None and not self._llm.serves("rank"): return None

        chosen = self._llm.prompt(provider) if provider is not None else self._llm.task("rank")

        return chosen.harness(self._policies.stage("ranking"))

    def identity ( self, provider: str | None = None ) -> str:

        return self.embedder(provider).provider().identity()

    async def embed ( self, texts: Sequence[str], query: bool = False, provider: str | None = None ) -> list[Embedding]:

        embedder = self.embedder(provider)
        guided   = self._settings.instruction if query else None
        size     = self._settings.batch
        found    : list[Embedding] = []

        for start in range(0, len(texts), size):

            found.extend((await embedder.embed(texts[start:start + size], query, guided)).vectors)

        if len(found) != len(texts): raise Fault(Code.UNAVAILABLE, reason="rag.embedding.count")

        return found

    async def scores (
        self, question: str, texts: Sequence[str], provider: str | None = None,
    ) -> tuple[Score, ...]:

        ranker = self.ranker(provider)

        if ranker is None or len(texts) < PAIR: return tuple(Score(index, 0.0) for index in range(len(texts)))

        return await ranker.rank(question, texts, self._settings.generative, native=self._settings.native)

    async def rank (
        self, question: str, passages: Sequence[Passage], provider: str | None = None,
    ) -> tuple[Passage, ...]:

        if self.ranker(provider) is None or len(passages) < PAIR: return tuple(passages)

        scored = await self.scores(question, [passage.text for passage in passages], provider)

        return tuple(replace(passages[score.index], score=score.score) for score in scored)

    async def search (
        self, index: Index, question: str, scope: str, rewrites: Sequence[str] = (),
    ) -> tuple[Passage, ...]:

        if not question.strip(): raise Fault(Code.VALIDATION, reason="rag.question")

        asked    = [question, *dict.fromkeys(text for text in rewrites if text.strip() and text != question)]
        vectors  = await self.embed(asked, query=True)
        identity = self.identity()
        found    = [
            await index.search(scope, text, vector, identity, self._settings.candidates)
            for text, vector in zip(asked, vectors, strict=True)
        ]
        merged   = found[0] if len(found) == 1 else self.fused(found, self._settings.candidates)

        return await self.rank(question, merged)

    def metrics ( self, retrieved: Sequence[Passage], relevant: Iterable[str], limit: int = 10 ) -> Metrics:

        documents = list(dict.fromkeys(passage.document for passage in retrieved))

        return Ranking().metrics(documents, relevant, limit)

    def fused (
        self, rankings: Sequence[Sequence[Passage]], limit: int | None = None, smoothing: int = 60,
    ) -> tuple[Passage, ...]:

        if smoothing < 1: raise Fault(Code.VALIDATION, reason="rag.fusion")

        scores : dict[str, float] = {}
        known  : dict[str, Passage] = {}

        for ranking in rankings:

            for place, passage in enumerate(ranking, 1):

                scores[passage.id] = scores.get(passage.id, 0.0) + 1.0 / (smoothing + place)
                known.setdefault(passage.id, passage)

        ordered = sorted(scores, key=lambda key: (-scores[key], key))

        return tuple(replace(known[key], score=round(scores[key], 6)) for key in ordered[:limit])
