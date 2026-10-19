from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from core.array import Metrics, Ranking
from core.error import Code, Fault
from core.fs import Converter, Extraction, ExtractPolicy
from core.json import json
from core.llm import Prompt
from core.number import Embedding
from core.string import string
from .context import GROUNDED, JUDGE, JUDGED, Context, judged
from .contract import Answer, Document, Evaluation, Index, Models, Passage, Policies, Row, Settings

KEY  = 32
PAIR = 2

class Rag:

    def __init__ (
        self, models: Models, index: Index, policies: Policies | None = None, settings: Settings | None = None,
    ) -> None:

        self._models   = models
        self._index    = index
        self._policies = policies or Policies()
        self._settings = settings or Settings()
        self._reader   = Extraction()

    def identity ( self ) -> str:

        return self._models.embedding.provider().identity()

    def stage ( self, prompt: Prompt, name: str ) -> Prompt:

        return prompt.harness(self._policies.stage(name))

    def passages ( self, document: Document, scope: str ) -> list[Passage]:

        if not document.id: raise Fault(Code.VALIDATION, reason="rag.document.id")

        found: list[Passage] = []

        for ordinal, part in enumerate(document.parts):

            for piece in string.chunks(part.text.replace("\x00", ""), self._settings.chunk, self._settings.overlap):

                if not piece.text.strip(): continue

                key = string.hash(json.dumps([scope, document.id, ordinal, piece.start, piece.text]), size=KEY)

                found.append(Passage(
                    key, document.id, document.source, piece.text, part.page, part.second, piece.start, piece.end,
                ))

        return found

    async def ingest ( self, documents: Sequence[Document], scope: str ) -> tuple[Passage, ...]:

        self._index.scoped(scope)

        if len({ document.id for document in documents }) != len(documents):
            raise Fault(Code.VALIDATION, reason="rag.documents.duplicate")

        planned  = [(document, self.passages(document, scope)) for document in documents]
        written  = [passage for _, passages in planned for passage in passages]
        vectors  = iter(await self.embedded([passage.text for passage in written]))
        identity = self.identity()

        for document, passages in planned:

            rows = [Row(passage, next(vectors)) for passage in passages]

            await self._index.replace(scope, document.id, rows, identity)

        return tuple(written)

    async def files (
        self, paths: Sequence[str | Path], scope: str, policy: ExtractPolicy | None = None,
        converter: Converter | None = None,
    ) -> tuple[Passage, ...]:

        documents: list[Document] = []

        for path in paths:

            extracted = await self._reader.extract(path, policy, converter)

            documents.append(Document(str(path), extracted.source, extracted.parts))

        return await self.ingest(documents, scope)

    async def upload (
        self, name: str, data: bytes, scope: str, key: str | None = None, policy: ExtractPolicy | None = None,
        converter: Converter | None = None,
    ) -> tuple[Passage, ...]:

        extracted = await self._reader.parse(name, data, policy, converter)

        return await self.ingest([Document(key or name, extracted.source, extracted.parts)], scope)

    async def embedded ( self, texts: Sequence[str], query: bool = False ) -> list[Embedding]:

        embedder = self.stage(self._models.embedding, "embedding")
        guided   = self._settings.instruction if query else None
        size     = self._settings.batch
        found: list[Embedding] = []

        for start in range(0, len(texts), size):

            found.extend((await embedder.embed(texts[start:start + size], query, guided)).vectors)

        return found

    async def retrieve ( self, question: str, scope: str ) -> tuple[Passage, ...]:

        if not question.strip(): raise Fault(Code.VALIDATION, reason="rag.question")

        vector = (await self.embedded([question], query=True))[0]
        found  = await self._index.search(scope, question, vector, self.identity(), self._settings.candidates)

        return await self.reranked(question, found)

    async def reranked ( self, question: str, passages: tuple[Passage, ...] ) -> tuple[Passage, ...]:

        ranker = self._models.ranking

        if ranker is None or len(passages) < PAIR: return passages

        texts  = [passage.text for passage in passages]
        scores = await self.stage(ranker, "ranking").rank(
            question, texts, self._settings.generative, native=self._settings.native,
        )

        return tuple(replace(passages[score.index], score=score.score) for score in scores)

    async def ask ( self, question: str, scope: str, generation: Prompt | None = None ) -> Answer:

        context = Context.build(question, await self.retrieve(question, scope), self._settings.context)
        writer  = self.stage(generation or self._models.generation, "generation").instruct(GROUNDED)
        reply   = await writer.schema(context.schema(), self._settings.native).ask(context.prompt)
        data    = reply.payload()

        return Answer(reply, str(data["answer"]), context.passages(), context.cited(data["citations"]))

    async def evaluate ( self, question: str, answer: Answer ) -> Evaluation:

        judge = self._models.evaluation

        if judge is None: raise Fault(Code.INTERNAL, reason="rag.evaluation.missing")

        asked = judged(question, answer.text, answer.passages)
        reply = await self.stage(judge, "evaluation").instruct(JUDGE).schema(JUDGED, self._settings.native).ask(asked)
        data  = reply.payload()

        return Evaluation(float(data["score"]), str(data["reasoning"]), reply.model)

    def metrics ( self, retrieved: Sequence[Passage], relevant: Iterable[str], limit: int = 10 ) -> Metrics:

        return Ranking().metrics(list(dict.fromkeys(passage.document for passage in retrieved)), relevant, limit)

    async def forget ( self, scope: str, document: str ) -> int:

        return await self._index.remove(scope, document)

    async def documents ( self, scope: str ) -> list[str]:

        return await self._index.documents(scope)

    async def count ( self, scope: str ) -> int:

        return await self._index.count(scope)

    async def clear ( self, scope: str ) -> int:

        return await self._index.clear(scope)

    def describe ( self ) -> dict[str, Any]:

        return {
            "index": self._index.describe(), "embedding": self.identity(), "ranking": self._models.ranking is not None,
            "evaluation": self._models.evaluation is not None, "candidates": self._settings.candidates,
            "context": self._settings.context, "native": self._settings.native,
        }
