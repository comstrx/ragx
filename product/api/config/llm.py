from typing import Any, ClassVar, Literal

from engine.config import Settings, field
from engine.llm import Effort, Model, Options, Task
from engine.validate import Shape

type Driver = Literal["chatgpt", "claude", "gemini", "deepseek", "local"]

WRITES  = ["complete", "stream", "models", "texts", "json", "schema"]
SEES    = [*WRITES, "images"]
VECTORS = ["embed", "instruct", "models"]
RANKS   = ["rank", "models"]
HEARS   = ["transcribe", "models"]

class Defaults(Shape):

    system      : str | None = None
    temperature : float | None = field(None, ge=0, le=2)
    max_tokens  : int | None = field(None, ge=1)
    top_p       : float | None = field(None, gt=0, le=1)
    top_k       : int | None = field(None, ge=1)
    stop        : list[str] = field(factory=list)
    seed        : int | None = None
    presence    : float | None = field(None, ge=-2, le=2)
    frequency   : float | None = field(None, ge=-2, le=2)
    effort      : Effort | None = None
    extra       : dict[str, Any] = field(factory=dict)

    def options ( self ) -> Options:

        return Options(
            system=self.system, temperature=self.temperature, max_tokens=self.max_tokens, top_p=self.top_p,
            top_k=self.top_k, stop=tuple(self.stop), seed=self.seed, presence=self.presence,
            frequency=self.frequency, effort=self.effort, extra=dict(self.extra),
        )

class Endpoint(Shape):

    hidden: ClassVar[tuple[str, ...]] = ("key",)

    driver   : Driver = "local"
    model    : str = ""
    url      : str = ""
    key      : str = ""
    tasks    : list[Task] = field(factory=list)
    serves   : list[str] | None = None
    headers  : dict[str, str] = field(factory=dict)
    timeout  : float = field(60.0, gt=0, le=600)
    retries  : int = field(1, ge=0, le=5)
    window   : int | None = field(None, ge=256)
    defaults : Defaults = field(factory=Defaults)

    def ready ( self ) -> bool:

        return bool(self.model and (self.url or self.key))

    def spec ( self, name: str ) -> Model:

        serves = frozenset(self.serves) if self.serves is not None else None

        return Model(
            self.model, self.url, self.key, name, self.driver, frozenset(self.tasks), serves,
            frozendict(self.headers), self.timeout, self.retries, self.window, self.defaults.options(),
        )

def local ( tasks: list[Task], serves: list[str], timeout: float = 120.0 ) -> Endpoint:

    return Endpoint(tasks=tasks, serves=serves, timeout=timeout, retries=0)

class LlmConfig(Settings, env_prefix="LLM_", nested_model_default_partial_update=True):

    default     : str = "writer"
    session_ttl : float = field(3600.0, gt=0)
    timeout     : float = field(120.0, gt=0, le=600)
    window      : int = field(8192, ge=256)
    compact     : float = field(0.7, gt=0, le=1)
    keep        : int = field(4, ge=2)
    tasks       : dict[Task, str] = field(factory=dict)
    writer      : Endpoint = local(["generate", "evaluate"], WRITES)
    summarizer  : Endpoint = local(["summarize"], WRITES)
    embedder    : Endpoint = local(["embed"], VECTORS)
    ranker      : Endpoint = local(["rank"], RANKS)
    vision      : Endpoint = local(["ocr", "describe"], SEES)
    listener    : Endpoint = local(["transcribe"], HEARS, 600.0)
    chatgpt     : Endpoint = Endpoint(driver="chatgpt")
    claude      : Endpoint = Endpoint(driver="claude")
    gemini      : Endpoint = Endpoint(driver="gemini")
    deepseek    : Endpoint = Endpoint(driver="deepseek")

    def endpoints ( self ) -> dict[str, Endpoint]:

        found = ((name, getattr(self, name)) for name in type(self).model_fields)

        return { name: entry for name, entry in found if isinstance(entry, Endpoint) }

    def models ( self ) -> list[Model]:

        return [entry.spec(name) for name, entry in self.endpoints().items() if entry.ready()]
