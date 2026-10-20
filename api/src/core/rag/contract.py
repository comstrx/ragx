from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar

from core.adapter import Adapter
from core.error import Code, Fault
from core.fs import Gap, Part
from core.llm import Harness, Reply
from core.number import Embedding

DENSE   = "dense"
LEXICAL = "lexical"
DURABLE = "durable"
STAGES  = ("generation", "embedding", "ranking", "evaluation", "extraction", "summary")

@dataclass(frozen=True, slots=True)
class Document:

    id     : str
    source : str
    parts  : tuple[Part, ...]
    mime   : str = "text/plain"
    gaps   : tuple[Gap, ...] = ()

    @classmethod
    def text ( cls, key: str, source: str, content: str ) -> Document:

        return cls(key, source, (Part(content),))

    def content ( self ) -> str:

        return "\n\n".join(part.text for part in self.parts)

    def complete ( self ) -> bool:

        return not self.gaps

@dataclass(frozen=True, slots=True)
class Passage:

    id       : str
    document : str
    source   : str
    text     : str
    page     : int | None = None
    second   : float | None = None
    start    : int = 0
    end      : int = 0
    score    : float = 0.0

@dataclass(frozen=True, slots=True)
class Row:

    passage   : Passage
    embedding : Embedding

@dataclass(frozen=True, slots=True)
class Answer:

    reply     : Reply
    text      : str
    passages  : tuple[Passage, ...]
    citations : tuple[Passage, ...]

@dataclass(frozen=True, slots=True)
class Evaluation:

    score     : float
    reasoning : str
    model     : str

@dataclass(frozen=True, slots=True)
class Summary:

    text   : str
    model  : str
    rounds : int
    pieces : int

@dataclass(frozen=True, slots=True)
class Policies:

    common     : Harness = field(default_factory=Harness)
    generation : Harness | None = None
    embedding  : Harness | None = None
    ranking    : Harness | None = None
    evaluation : Harness | None = None
    extraction : Harness | None = None
    summary    : Harness | None = None

    def stage ( self, name: str ) -> Harness:

        if name not in STAGES: raise Fault(Code.INTERNAL, reason=f"rag.stage.{name}")

        chosen: Harness | None = getattr(self, name)

        return self.common.merge(chosen) if chosen is not None else self.common

@dataclass(frozen=True, slots=True)
class Settings:

    chunk       : int = 800
    overlap     : int = 80
    candidates  : int = 8
    context     : int = 6000
    batch       : int = 32
    native      : bool = True
    generative  : bool = False
    instruction : str | None = None
    partial     : bool = True
    span        : float = 600.0
    frames      : int = 8
    scale       : float = 2.0
    language    : str | None = None
    digest      : int = 12_000

    def __post_init__ ( self ) -> None:

        positive = min(self.chunk, self.candidates, self.context, self.batch, self.frames, self.digest) > 0
        timed    = self.span > 0 and self.scale > 0

        if not positive or not timed or not 0 <= self.overlap < self.chunk:
            raise Fault(Code.VALIDATION, reason="rag.settings")

class Index(Adapter, ABC):

    family       : ClassVar[str] = "rag"
    capabilities : ClassVar[frozenset[str]] = frozenset({DENSE, LEXICAL})
    name         = "index"

    def scoped ( self, scope: str ) -> str:

        if not scope: raise Fault(Code.FORBIDDEN, reason="rag.scope")

        return scope

    @abstractmethod
    async def replace ( self, scope: str, document: str, rows: Sequence[Row], identity: str ) -> int: ...

    @abstractmethod
    async def remove ( self, scope: str, document: str ) -> int: ...

    @abstractmethod
    async def search (
        self, scope: str, query: str, embedding: Embedding, identity: str, limit: int,
    ) -> tuple[Passage, ...]: ...

    @abstractmethod
    async def documents ( self, scope: str ) -> list[str]: ...

    @abstractmethod
    async def count ( self, scope: str ) -> int: ...

    @abstractmethod
    async def clear ( self, scope: str ) -> int: ...
