from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, override

from engine.error import Code, Fault
from engine.json import Schema
from engine.log import log
from engine.net import Remote, Sse, Transport
from .message import Attachment, Chunk, Message, Options, Reply
from .result import Embeddings, Score, Transcript

COMPLETE   = "complete"
STREAM     = "stream"
MODELS     = "models"
JSON       = "json"
SCHEMA     = "schema"
METADATA   = "metadata"
IMAGES     = "images"
DOCUMENTS  = "documents"
TEXTS      = "texts"
AUDIO      = "audio"
VIDEO      = "video"
EMBED      = "embed"
RANK       = "rank"
INSTRUCT   = "instruct"
TOKENS     = "tokens"
TRANSCRIBE = "transcribe"
CORE       = frozenset({COMPLETE, STREAM, MODELS, TEXTS})
VECTORS    = frozenset({EMBED, MODELS})
HEARING    = frozenset({TRANSCRIBE, MODELS})
KNOWN      = frozenset({
    COMPLETE, STREAM, MODELS, JSON, SCHEMA, METADATA, IMAGES, DOCUMENTS, TEXTS, AUDIO, VIDEO, EMBED, RANK, INSTRUCT,
    TOKENS, TRANSCRIBE,
})
SMALLEST   = 256
NEEDS      : Mapping[str, tuple[frozenset[str], ...]] = frozendict({
    "generate"   : (frozenset({COMPLETE}),),
    "summarize"  : (frozenset({COMPLETE}),),
    "evaluate"   : (frozenset({COMPLETE}),),
    "embed"      : (frozenset({EMBED}),),
    "rank"       : (frozenset({RANK}), frozenset({COMPLETE})),
    "ocr"        : (frozenset({COMPLETE, IMAGES}),),
    "describe"   : (frozenset({COMPLETE, IMAGES}),),
    "transcribe" : (frozenset({TRANSCRIBE}), frozenset({COMPLETE, AUDIO})),
})

type Task = Literal["generate", "summarize", "evaluate", "embed", "rank", "ocr", "describe", "transcribe"]

@dataclass(frozen=True, slots=True)
class Model:

    model   : str = ""
    url     : str = ""
    key     : str = field(default="", repr=False)
    name    : str = ""
    driver  : str = ""
    tasks   : frozenset[str] = frozenset()
    serves  : frozenset[str] | None = None
    headers : Mapping[str, str] = field(default_factory=frozendict, repr=False)
    timeout : float = 60.0
    retries : int = 1
    window  : int | None = None
    options : Options = field(default_factory=Options)

    def __post_init__ ( self ) -> None:

        unknown = sorted(self.tasks - NEEDS.keys())
        foreign = sorted((self.serves or frozenset()) - KNOWN)

        if unknown: raise Fault(Code.INTERNAL, reason=f"llm.task.{unknown[0]}")
        if foreign: raise Fault(Code.INTERNAL, reason=f"llm.capability.{foreign[0]}")
        if self.timeout <= 0 or self.retries < 0: raise Fault(Code.INTERNAL, reason="llm.model.limits")
        if self.window is not None and self.window < SMALLEST: raise Fault(Code.INTERNAL, reason="llm.model.window")

class Provider(Remote, ABC):

    family       : ClassVar[str] = "llm"
    capabilities : ClassVar[frozenset[str]] = CORE
    tunes        : ClassVar[frozenset[str]] = frozenset()
    efforts      : ClassVar[frozenset[str]] = frozenset()
    base         : ClassVar[str] = ""
    keyed        : ClassVar[bool] = False
    model        : str = ""

    def __init__ ( self, spec: Model, transport: Transport | None = None ) -> None:

        if spec.name: self.name = spec.name
        if self.keyed: self.missing(("key", spec.key))

        self.missing(("url", spec.url or self.base), ("model", spec.model))

        super().__init__(spec.url or self.base, spec.timeout, spec.retries, transport, spec.headers)

        self.spec    = spec
        self.model   = spec.model
        self._key    = spec.key
        self._serves = spec.serves

    @override
    def abilities ( self ) -> frozenset[str]:

        return self._serves if self._serves is not None else type(self).capabilities

    def able ( self, task: str ) -> bool:

        return any(need <= self.abilities() for need in NEEDS.get(task, ()))

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._key}" } if self._key else {}

    def identity ( self ) -> str:

        return f"{self.name}:{self.model}"

    def pick ( self, options: Options ) -> str:

        return options.model or self.model

    def tuned ( self, options: Options ) -> dict[str, Any]:

        found = { name: value for name, value in options.tuning().items() if name in self.tunes }

        if "effort" in found and found["effort"] not in self.efforts: found.pop("effort")

        return found

    def check ( self, messages: Sequence[Message], options: Options ) -> None:

        if options.json: self.require(JSON)
        if options.schema is not None and options.native: self.require(SCHEMA)
        if options.metadata: self.require(METADATA)

        for message in messages:

            for attachment in message.attachments: self.require(attachment.kind())

        ignored = sorted(options.tuning().keys() - self.tuned(options).keys())

        if ignored: log.debug("llm.options.ignored", provider=self.name, options=ignored)

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

    async def count ( self, messages: Sequence[Message], options: Options ) -> int:

        self.require(TOKENS)

        return await self.tally(messages, options)

    async def transcribe ( self, media: Attachment, language: str | None = None ) -> Transcript:

        self.require(TRANSCRIBE)

        if not media.mime.startswith(("audio/", "video/")): raise Fault(Code.VALIDATION, reason="llm.transcribe.media")

        return await self.listen(media, language)

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

    async def tally ( self, messages: Sequence[Message], options: Options ) -> int:

        raise self.unsupported(TOKENS)

    async def listen ( self, media: Attachment, language: str | None ) -> Transcript:

        raise self.unsupported(TRANSCRIBE)

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

        return {
            **super().describe(), "model": self.model, "keyed": bool(self._key), "tasks": sorted(self.spec.tasks),
            "tunes": sorted(self.tunes), "efforts": sorted(self.efforts),
        }

def text_of ( value: object ) -> str:

    if isinstance(value, str): return value
    if isinstance(value, list):
        return "".join(str(part.get("text", "")) for part in value if isinstance(part, dict))

    return ""
