from collections.abc import AsyncGenerator, Iterable, Sequence
from pathlib import Path
from typing import Any, Self, Unpack

from engine.array import Metrics
from engine.error import Code, Fault
from engine.fs import ExtractPolicy
from engine.json import json
from engine.llm import Chunk, Llm, Score, Tuning, llm
from engine.number import Embedding
from engine.string import string
from .contract import Answer, Document, Evaluation, Index, Passage, Policies, Row, Settings, Summary
from .evaluate import Judge, Quality
from .extract import Reader
from .generate import Context, Writer
from .retrieve import Retriever

KEY = 32

class Rag:

    def __init__ ( self ) -> None:

        self._index    : Index | None = None
        self._llm      = llm
        self._policies = Policies()
        self._settings = Settings()

        self.build()

    def setup (
        self, index: Index | None = None, brain: Llm | None = None, policies: Policies | None = None,
        settings: Settings | None = None,
    ) -> Self:

        self._index    = index or self._index
        self._llm      = brain or self._llm
        self._policies = policies or self._policies
        self._settings = settings or self._settings

        self.build()

        return self

    def build ( self ) -> None:

        self._reader    = Reader(self._llm, self._policies, self._settings)
        self._retriever = Retriever(self._llm, self._policies, self._settings)
        self._writer    = Writer(self._llm, self._policies, self._settings)
        self._judge     = Judge(self._llm, self._policies, self._settings)

    def index ( self ) -> Index:

        if self._index is None: raise Fault(Code.INTERNAL, reason="rag.index.missing")

        return self._index

    def identity ( self ) -> str:

        return self._retriever.identity()

    async def extract (
        self, name: str, data: bytes, key: str | None = None, policy: ExtractPolicy | None = None,
    ) -> Document:

        return await self._reader.read(name, data, key, policy)

    async def read ( self, path: str | Path, key: str | None = None, policy: ExtractPolicy | None = None ) -> Document:

        return await self._reader.file(path, key, policy)

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

        index = self.index()

        index.scoped(scope)

        if len({ document.id for document in documents }) != len(documents):
            raise Fault(Code.VALIDATION, reason="rag.documents.duplicate")

        planned  = [(document, self.passages(document, scope)) for document in documents]
        written  = [passage for _, passages in planned for passage in passages]
        vectors  = iter(await self.embed([passage.text for passage in written]))
        identity = self.identity()

        for document, passages in planned:

            await index.replace(scope, document.id, [Row(passage, next(vectors)) for passage in passages], identity)

        return tuple(written)

    async def files (
        self, paths: Sequence[str | Path], scope: str, policy: ExtractPolicy | None = None,
    ) -> tuple[Passage, ...]:

        return await self.ingest([await self.read(path, policy=policy) for path in paths], scope)

    async def upload (
        self, name: str, data: bytes, scope: str, key: str | None = None, policy: ExtractPolicy | None = None,
    ) -> tuple[Passage, ...]:

        return await self.ingest([await self.extract(name, data, key, policy)], scope)

    async def embed (
        self, texts: Sequence[str], query: bool = False, provider: str | None = None,
    ) -> list[Embedding]:

        return await self._retriever.embed(texts, query, provider)

    async def scores (
        self, question: str, texts: Sequence[str], provider: str | None = None,
    ) -> tuple[Score, ...]:

        return await self._retriever.scores(question, texts, provider)

    async def rank (
        self, question: str, passages: Sequence[Passage], provider: str | None = None,
    ) -> tuple[Passage, ...]:

        return await self._retriever.rank(question, passages, provider)

    def fuse ( self, rankings: Sequence[Sequence[Passage]], limit: int | None = None ) -> tuple[Passage, ...]:

        return self._retriever.fused(rankings, limit)

    async def retrieve ( self, question: str, scope: str, rewrites: Sequence[str] = () ) -> tuple[Passage, ...]:

        return await self._retriever.search(self.index(), question, scope, rewrites)

    async def grounding ( self, question: str, scope: str, rewrites: Sequence[str] = () ) -> Context:

        return Context.build(question, await self.retrieve(question, scope, rewrites), self._settings.context)

    async def ask (
        self, question: str, scope: str, provider: str | None = None, session: str | None = None,
        **tuning: Unpack[Tuning],
    ) -> Answer:

        return await self._writer.ask(await self.grounding(question, scope), provider, session, **tuning)

    async def stream (
        self, question: str, scope: str, provider: str | None = None, session: str | None = None,
        **tuning: Unpack[Tuning],
    ) -> AsyncGenerator[Chunk | Answer]:

        context = await self.grounding(question, scope)

        async for item in self._writer.stream(question, context, provider, session, **tuning): yield item

    async def summarize (
        self, source: str | Document, provider: str | None = None, focus: str | None = None,
        **tuning: Unpack[Tuning],
    ) -> Summary:

        text = source.content() if isinstance(source, Document) else source

        return await self._writer.summarize(text, provider, focus, **tuning)

    async def evaluate ( self, question: str, answer: Answer, provider: str | None = None ) -> Evaluation:

        return await self._judge.evaluate(question, answer, provider)

    def metrics ( self, retrieved: Sequence[Passage], relevant: Iterable[str], limit: int = 10 ) -> Metrics:

        return self._retriever.metrics(retrieved, relevant, limit)

    def quality ( self, scope: str, limit: int = 3, recall: float = 1.0, floor: float | None = None ) -> Quality:

        return Quality(self, scope, limit, recall, floor)

    async def forget ( self, scope: str, document: str ) -> bool:

        return await self.index().remove(scope, document) > 0

    async def documents ( self, scope: str ) -> list[str]:

        return await self.index().documents(scope)

    async def count ( self, scope: str ) -> int:

        return await self.index().count(scope)

    async def clear ( self, scope: str ) -> int:

        return await self.index().clear(scope)

    def describe ( self ) -> dict[str, Any]:

        tasks = self._llm.tasks()

        return {
            "index": self._index.describe() if self._index is not None else None, "tasks": tasks,
            "candidates": self._settings.candidates, "context": self._settings.context,
            "native": self._settings.native, "partial": self._settings.partial,
        }
