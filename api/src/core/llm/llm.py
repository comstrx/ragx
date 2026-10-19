from collections.abc import AsyncIterator, Sequence
from typing import Any, Unpack, override

from core.adapter import Manager
from core.error import Code, Fault
from .embedding import Embeddings, Score
from .harness import Harness, Memory
from .message import Attachment, Chunk, Message, Reply, Tuning
from .prompt import Prompt
from .provider import Provider
from .session import HOUR, Ledger, Session, Sessions
import math

CHARS_PER_TOKEN = 4

class Llm(Manager[Provider]):

    def __init__ ( self ) -> None:

        super().__init__("llm")

        self.sessions = Sessions()
        self._harness = Harness()
        self._memory  = Memory()

    def setup (
        self, default: str | None = None, ttl: float | None = None, harness: Harness | None = None,
        memory: Memory | None = None, ledger: Ledger | None = None,
    ) -> None:

        if ttl is not None or ledger is not None: self.sessions = Sessions(ttl or HOUR, ledger=ledger)
        if default is not None: self._default = default
        if harness is not None: self._harness = harness
        if memory is not None: self._memory = memory

    def harness ( self ) -> Harness:

        return self._harness

    def prompt ( self, name: str | None = None ) -> Prompt:

        return Prompt(self.use(name), self.sessions, self._harness, self._memory)

    def local ( self ) -> Prompt:

        return self.prompt("local")

    def chatgpt ( self ) -> Prompt:

        return self.prompt("chatgpt")

    def claude ( self ) -> Prompt:

        return self.prompt("claude")

    def gemini ( self ) -> Prompt:

        return self.prompt("gemini")

    def deepseek ( self ) -> Prompt:

        return self.prompt("deepseek")

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

        return { **super().describe(), **self.sessions.describe() }
