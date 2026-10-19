from dataclasses import dataclass, field
from typing import Literal
from core.error import Code, Fault
from core.fs import Artifact
from core.net import DownloadPolicy

MIN_CONTEXT = 128

type Purpose = Literal["generate", "embed", "rank"]

@dataclass(frozen=True, slots=True)
class Source:

    url      : str
    artifact : Artifact
    revision : str

@dataclass(frozen=True, slots=True)
class LocalModel:

    source        : Source
    runtime       : Source
    name          : str
    purpose       : Purpose = "generate"
    path          : str = ".runtime"
    threads       : int = 2
    context       : int = 2048
    batch         : int = 256
    startup       : float = 90.0
    embedding_format : Literal["plain", "qwen3"] = "plain"
    policy        : DownloadPolicy = field(default_factory=DownloadPolicy)

    def __post_init__ ( self ) -> None:

        if self.purpose not in ("generate", "embed", "rank") or self.embedding_format not in ("plain", "qwen3"):
            raise Fault(Code.VALIDATION, reason="llm.local.profile")
        if self.threads < 1 or self.context < MIN_CONTEXT or self.batch < 1 or self.startup <= 0:
            raise Fault(Code.VALIDATION, reason="llm.local.limits")
