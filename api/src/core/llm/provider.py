from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence
from typing import Any, ClassVar, override

from core.json import Schema
from core.net import Remote, Sse, Transport
from .embedding import Embeddings, Score
from .message import Chunk, Message, Options, Reply

COMPLETE  = "complete"
STREAM    = "stream"
MODELS    = "models"
JSON      = "json"
SCHEMA    = "schema"
METADATA  = "metadata"
IMAGES    = "images"
DOCUMENTS = "documents"
TEXTS     = "texts"
AUDIO     = "audio"
VIDEO     = "video"
EMBED     = "embed"
RANK      = "rank"
INSTRUCT  = "instruct"
CORE      = frozenset({COMPLETE, STREAM, MODELS, TEXTS})
VECTORS   = frozenset({EMBED, MODELS})

class Provider(Remote, ABC):

    family       : ClassVar[str] = "llm"
    capabilities : ClassVar[frozenset[str]] = CORE
    model        : str = ""

    def __init__ (
        self, base: str, key: str = "", model: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: Transport | None = None, serves: Iterable[str] | None = None, name: str | None = None,
    ) -> None:

        super().__init__(base, wait, retries, transport)

        self._key    = key
        self._serves = frozenset(serves) if serves is not None else None

        if model: self.model = model
        if name: self.name = name

    @override
    def abilities ( self ) -> frozenset[str]:

        return self._serves if self._serves is not None else type(self).capabilities

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._key}" } if self._key else {}

    def identity ( self ) -> str:

        return f"{self.name}:{self.model}"

    def pick ( self, options: Options ) -> str:

        return options.model or self.model

    def check ( self, messages: Sequence[Message], options: Options ) -> None:

        if options.json: self.require(JSON)
        if options.schema is not None and options.native: self.require(SCHEMA)
        if options.metadata: self.require(METADATA)

        for message in messages:

            for attachment in message.attachments: self.require(attachment.kind())

    async def complete ( self, messages: Sequence[Message], options: Options ) -> Reply:

        self.require(COMPLETE)
        self.check(messages, options)

        return await self.answer(messages, options)

    def stream ( self, messages: Sequence[Message], options: Options ) -> AsyncGenerator[Chunk]:

        self.require(STREAM)
        self.check(messages, options)

        return self.chunks(messages, options)

    async def embed ( self, texts: Sequence[str], query: bool = False, instruction: str | None = None ) -> Embeddings:

        self.require(EMBED)

        return await self.vectors(texts, query, instruction)

    async def rank ( self, query: str, documents: Sequence[str] ) -> tuple[Score, ...]:

        self.require(RANK)

        return await self.scores(query, documents)

    @abstractmethod
    async def answer ( self, messages: Sequence[Message], options: Options ) -> Reply: ...

    @abstractmethod
    def chunks ( self, messages: Sequence[Message], options: Options ) -> AsyncGenerator[Chunk]: ...

    @abstractmethod
    async def models ( self ) -> list[str]: ...

    async def vectors ( self, texts: Sequence[str], query: bool, instruction: str | None ) -> Embeddings:

        raise self.unsupported(EMBED)

    async def scores ( self, query: str, documents: Sequence[str] ) -> tuple[Score, ...]:

        raise self.unsupported(RANK)

    def shaped ( self, schema: Schema ) -> dict[str, Any]:

        return schema.dump()

    async def post ( self, path: str, body: Mapping[str, Any], action: str = COMPLETE ) -> Any:

        return await self.call("POST", path, action, json=body)

    async def listing ( self, path: str ) -> Any:

        return await self.call("GET", path, MODELS)

    def flow ( self, path: str, body: Mapping[str, Any] ) -> AsyncGenerator[Sse]:

        return self.events("POST", path, STREAM, body)

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "model": self.model, "keyed": bool(self._key) }

def text_of ( value: object ) -> str:

    if isinstance(value, str): return value
    if isinstance(value, list):
        return "".join(str(part.get("text", "")) for part in value if isinstance(part, dict))

    return ""
