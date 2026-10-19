from dataclasses import dataclass, field
from core.llm import Harness, Prompt, RankingOptions, Reply
from core.fs import Part

@dataclass(frozen=True, slots=True)
class Models:

    generation : Prompt
    embedding  : Prompt
    ranking    : Prompt | None = None
    evaluation : Prompt | None = None

@dataclass(frozen=True, slots=True)
class Policies:

    common     : Harness = field(default_factory=Harness)
    generation : Harness | None = None
    embedding  : Harness | None = None
    ranking    : Harness | None = None
    evaluation : Harness | None = None

    def for_stage ( self, stage: str ) -> Harness:

        policy: Harness | None = getattr(self, stage)
        return self.common.merge(policy) if policy is not None else self.common

@dataclass(frozen=True, slots=True)
class Document:

    id     : str
    source : str
    parts  : tuple[Part, ...]

@dataclass(frozen=True, slots=True)
class Passage:

    id     : str
    source : str
    text   : str
    page   : int | None = None
    second : float | None = None
    start  : int = 0
    end    : int = 0
    score  : float = 0.0

@dataclass(frozen=True, slots=True)
class Answer:

    reply     : Reply
    passages  : tuple[Passage, ...]
    citations : tuple[str, ...]

@dataclass(frozen=True, slots=True)
class Evaluation:

    score     : float
    reasoning : str
    model     : str

@dataclass(frozen=True, slots=True)
class RagOptions:

    chunk_chars   : int = 800
    overlap_chars : int = 80
    candidates    : int = 8
    context_chars : int = 6000
    capacity      : int = 10_000
    native_schema : bool = True
    ranking       : RankingOptions = field(default_factory=RankingOptions)
