from collections.abc import AsyncIterator, Sequence
from typing import Any

from core.error import Code, Fault
from .message import Attachment, Chunk, Message, Reply
from .prompt import Prompt
from .provider import Provider
from .session import Session, Sessions
import math

CHARS_PER_TOKEN = 4

class Llm:

    def __init__ ( self ) -> None:

        self._providers: dict[str, Provider] = {}
        self._default: str | None = None
        self.sessions = Sessions()

    def setup ( self, default: str | None = None, ttl: float | None = None ) -> None:

        if ttl is not None: self.sessions = Sessions(ttl)
        if default is not None: self._default = default

    def register ( self, provider: Provider, default: bool = False ) -> Provider:

        self._providers[provider.name] = provider

        if default or self._default is None: self._default = provider.name

        return provider

    def forget ( self, name: str ) -> bool:

        gone = self._providers.pop(name, None) is not None

        if self._default == name: self._default = next(iter(self._providers), None)

        return gone

    def ready ( self ) -> bool:
        return self._default is not None and self._default in self._providers

    def names ( self ) -> list[str]:
        return sorted(self._providers)

    def default ( self ) -> str | None:
        return self._default

    def provider ( self, name: str | None = None ) -> Provider:

        chosen = name or self._default
        found  = self._providers.get(chosen or "")

        if found is None: raise Fault(Code.INTERNAL, reason=f"llm.{chosen or 'default'}")

        return found

    def use ( self, name: str | None = None ) -> Prompt:
        return Prompt(self.provider(name), self.sessions)

    def local ( self ) -> Prompt:
        return self.use("local")

    def chatgpt ( self ) -> Prompt:
        return self.use("chatgpt")

    def claude ( self ) -> Prompt:
        return self.use("claude")

    def gemini ( self ) -> Prompt:
        return self.use("gemini")

    def deepseek ( self ) -> Prompt:
        return self.use("deepseek")

    async def ask (
        self, text: str, provider: str | None = None, system: str | None = None, model: str | None = None,
        files: Sequence[Attachment] = (), session: str | None = None, **options: Any,
    ) -> Reply:
        return await self.prompt(provider, system, model, files, session, **options).ask(text)

    def stream (
        self, text: str, provider: str | None = None, system: str | None = None, model: str | None = None,
        files: Sequence[Attachment] = (), session: str | None = None, **options: Any,
    ) -> AsyncIterator[Chunk]:
        return self.prompt(provider, system, model, files, session, **options).stream(text)

    def prompt (
        self, provider: str | None, system: str | None, model: str | None, files: Sequence[Attachment],
        session: str | None, **options: Any,
    ) -> Prompt:

        built = self.use(provider).configure(system=system, model=model, **options).attach(*files)

        return built.session(session) if session is not None else built

    def session (
        self, key: str | None = None, provider: str | None = None, model: str | None = None, system: str | None = None,
        history: Sequence[Message] = (),
    ) -> Session:

        if key is not None and self.sessions.has(key): return self.sessions.resume(key)

        return self.sessions.new(self.provider(provider).name, model, system, key, history)

    def resume ( self, key: str ) -> Prompt:

        session = self.sessions.resume(key)

        return self.use(session.provider).resume(key)

    def estimate_tokens ( self, text: str ) -> int:
        return math.ceil(len(text) / CHARS_PER_TOKEN)

    def fits ( self, text: str, budget: int ) -> bool:
        return self.estimate_tokens(text) <= budget

    async def models ( self, provider: str | None = None ) -> list[str]:
        return await self.provider(provider).models()

    async def close ( self ) -> None:

        for provider in self._providers.values(): await provider.close()

    def describe ( self ) -> dict[str, Any]:
        return { "default": self._default, "providers": self.names(), **self.sessions.describe() }
