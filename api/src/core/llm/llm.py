from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import Any, Unpack, override

from core.adapter import Manager
from core.error import Code, Fault
from .claude import Claude
from .compatible import ChatGpt, DeepSeek, Local
from .gemini import Gemini
from .harness import Harness, Memory
from .message import Attachment, Chunk, Message, Reply, Tuning
from .prompt import Prompt
from .provider import NEEDS, Model, Provider, Task
from .result import Embeddings, Score, Transcript
from .session import HOUR, Ledger, Session, Sessions
import math

CHARS_PER_TOKEN = 4
DRIVERS         : Mapping[str, type[Provider]] = frozendict({
    "chatgpt"  : ChatGpt,
    "claude"   : Claude,
    "gemini"   : Gemini,
    "deepseek" : DeepSeek,
    "local"    : Local,
})

class Llm(Manager[Provider]):

    def __init__ ( self ) -> None:

        super().__init__("llm")

        self.sessions = Sessions()
        self._harness = Harness()
        self._memory  = Memory()
        self._tasks: dict[str, str] = {}

    def setup (
        self, models: Sequence[Model] = (), default: str | None = None, ttl: float | None = None,
        harness: Harness | None = None, memory: Memory | None = None, ledger: Ledger | None = None,
        tasks: Mapping[Task, str] | None = None,
    ) -> None:

        if ttl is not None or ledger is not None: self.sessions = Sessions(ttl or HOUR, ledger=ledger)
        if harness is not None: self._harness = harness
        if memory is not None: self._memory = memory

        for spec in models: self.register(self.build(spec))
        for task, name in (tasks or {}).items(): self.assign(task, name)

        if default is not None: self.default(default)

    def build ( self, spec: Model ) -> Provider:

        kind = DRIVERS.get(spec.driver)

        if kind is None: raise Fault(Code.INTERNAL, reason=f"llm.driver.{spec.driver or 'missing'}")

        return kind(spec)

    @override
    def register ( self, adapter: Provider, default: bool = False ) -> Provider:

        unable = sorted(task for task in adapter.spec.tasks if not adapter.able(task))

        if unable: raise Fault(Code.INTERNAL, reason=f"llm.{adapter.name}.task.{unable[0]}")

        super().register(adapter, default)

        for task in adapter.spec.tasks: self._tasks.setdefault(task, adapter.name)

        return adapter

    def assign ( self, task: str, name: str ) -> None:

        if task not in NEEDS: raise Fault(Code.INTERNAL, reason=f"llm.task.{task}")
        if not self.use(name).able(task): raise Fault(Code.INTERNAL, reason=f"llm.{name}.task.{task}")

        self._tasks[task] = name

    def tasks ( self ) -> dict[str, str]:

        return dict(self._tasks)

    def serves ( self, task: str ) -> bool:

        return task in self._tasks

    def task ( self, name: str ) -> Prompt:

        chosen = self._tasks.get(name)

        if chosen is None: raise Fault(Code.INTERNAL, reason=f"llm.task.{name}.missing")

        return self.prompt(chosen)

    @override
    def forget ( self, name: str ) -> bool:

        self._tasks = { task: chosen for task, chosen in self._tasks.items() if chosen != name }

        return super().forget(name)

    @override
    def clear ( self ) -> int:

        self._tasks.clear()

        return super().clear()

    def harness ( self ) -> Harness:

        return self._harness

    def prompt ( self, name: str | None = None ) -> Prompt:

        provider   = self.use(name)
        window     = provider.spec.window
        memory     = replace(self._memory, window=window) if window is not None else self._memory
        summarizer = self.use(self._tasks["summarize"]) if "summarize" in self._tasks else None

        return Prompt(provider, self.sessions, self._harness, memory, summarizer)

    async def ask (
        self, text: str, provider: str | None = None, files: Sequence[Attachment] = (), session: str | None = None,
        **tuning: Unpack[Tuning],
    ) -> Reply:

        return await self.compose(provider, files, session, **tuning).ask(text)

    def stream (
        self, text: str, provider: str | None = None, files: Sequence[Attachment] = (), session: str | None = None,
        **tuning: Unpack[Tuning],
    ) -> AsyncIterator[Chunk]:

        return self.compose(provider, files, session, **tuning).stream(text)

    def compose (
        self, provider: str | None, files: Sequence[Attachment], session: str | None, **tuning: Unpack[Tuning],
    ) -> Prompt:

        built = self.prompt(provider).configure(**tuning).attach(*files)

        return built.session(session) if session is not None else built

    async def embed (
        self, texts: Sequence[str], provider: str | None = None, query: bool = False, instruction: str | None = None,
    ) -> Embeddings:

        return await self.prompt(provider).embed(texts, query, instruction)

    async def rank ( self, query: str, documents: Sequence[str], provider: str | None = None ) -> tuple[Score, ...]:

        return await self.prompt(provider).rank(query, documents)

    async def transcribe (
        self, media: Attachment, provider: str | None = None, language: str | None = None,
    ) -> Transcript:

        return await self.prompt(provider).transcribe(media, language)

    def session (
        self, key: str | None = None, provider: str | None = None, model: str | None = None, system: str | None = None,
        history: Sequence[Message] = (),
    ) -> Session:

        if key is not None and self.sessions.has(key): return self.sessions.resume(key)

        return self.sessions.new(self.use(provider).name, model, system, key, history)

    def resume ( self, key: str ) -> Prompt:

        session = self.sessions.resume(key)

        return self.prompt(session.provider).resume(key)

    async def restore ( self, key: str ) -> Prompt:

        session = await self.sessions.restore(key)

        if session is None: raise Fault(Code.NOT_FOUND, reason="llm.session.missing")

        return self.prompt(session.provider if self.has(session.provider) else None).resume(key)

    def estimate_tokens ( self, text: str ) -> int:

        return math.ceil(len(text) / CHARS_PER_TOKEN)

    def fits ( self, text: str, budget: int ) -> bool:

        return self.estimate_tokens(text) <= budget

    async def models ( self, provider: str | None = None ) -> list[str]:

        return await self.use(provider).models()

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "tasks": self.tasks(), **self.sessions.describe() }
