from collections.abc import AsyncIterator, Sequence
from typing import Any

from core.error import Code, Fault
from .message import Attachment, Chunk, Message, Reply
from .prompt import Prompt
from .provider import Provider
from .local import Local
from .model import LocalModel
from core.thread import thread
from .session import Session, Sessions
from .harness import Harness
import math

CHARS_PER_TOKEN = 4

class Llm:

    def __init__ ( self ) -> None:

        self._providers: dict[str, Provider] = {}
        self._default: str | None = None
        self.sessions = Sessions()
        self._harness = Harness()

    def setup (
        self, default: str | None = None, ttl: float | None = None, path: str | None = None,
        harness: Harness | None = None,
    ) -> None:

        if ttl is not None or path is not None: self.sessions = Sessions(ttl or 3600, path=path)
        if default is not None: self._default = default
        if harness is not None: self._harness = harness

    def register ( self, provider: Provider | LocalModel, default: bool = False, name: str | None = None ) -> Provider:

        if any(provider is existing for existing in self._providers.values()):
            raise Fault(Code.CONFLICT, reason="llm.provider.registered")
        if isinstance(provider, LocalModel): provider = Local(provider, name=name or "local")
        elif name is not None: provider.name = name

        if provider.name in self._providers: raise Fault(Code.CONFLICT, reason="llm.provider.exists")

        self._providers[provider.name] = provider

        if default or self._default is None: self._default = provider.name

        return provider

    async def forget ( self, name: str ) -> bool:

        provider = self._providers.get(name)
        if provider is None: return False
        await provider.close()
        gone = self._providers.pop(name, None) is not None

        if self._default == name: self._default = next(iter(self._providers), None)

        return gone

    def ready ( self ) -> bool:

        return self._default is not None and self._default in self._providers and self.provider().ready()

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

        return Prompt(self.provider(name), self.sessions, self._harness)

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

        chosen = self.provider(provider)
        return self.sessions.new(chosen.name, model or chosen.model, system, key, history)

    def resume ( self, key: str ) -> Prompt:

        session = self.sessions.resume(key)

        return self.use(session.provider).model(session.model or self.provider(session.provider).model).resume(key)

    def estimate_tokens ( self, text: str ) -> int:

        return math.ceil(len(text) / CHARS_PER_TOKEN)

    def fits ( self, text: str, budget: int ) -> bool:

        return self.estimate_tokens(text) <= budget

    async def models ( self, provider: str | None = None ) -> list[str]:

        return await self.provider(provider).models()

    async def start ( self, provider: str | None = None ) -> None:

        await self.provider(provider).start()

    async def restore ( self, key: str ) -> Prompt:

        session = await self.sessions.restore(key)

        return self.use(session.provider).model(session.model or self.provider(session.provider).model).resume(key)

    async def close ( self ) -> None:

        outcomes = await thread.settle(*(provider.close() for provider in self._providers.values()))
        for result in outcomes:
            if isinstance(result, BaseException): raise result

    def describe ( self ) -> dict[str, Any]:

        return { "default": self._default, "providers": self.names(), **self.sessions.describe() }
