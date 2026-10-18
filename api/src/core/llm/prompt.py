from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, Self

from core.log import log
from .message import Attachment, Chunk, Message, Options, Reply, Usage
from .provider import Provider
from .session import Session, Sessions

class Prompt:

    def __init__ ( self, provider: Provider, sessions: Sessions ) -> None:

        self._provider = provider
        self._sessions = sessions
        self._options  = Options()
        self._files: list[Attachment] = []
        self._history: list[Message] = []
        self._session: Session | None = None

    def provider ( self ) -> Provider:
        return self._provider

    def options ( self ) -> Options:
        return self._options

    def model ( self, name: str ) -> Self:
        return self.configure(model=name)

    def system ( self, text: str ) -> Self:
        return self.configure(system=text)

    def temperature ( self, value: float ) -> Self:
        return self.configure(temperature=value)

    def max_tokens ( self, count: int ) -> Self:
        return self.configure(max_tokens=count)

    def top_p ( self, value: float ) -> Self:
        return self.configure(top_p=value)

    def stop ( self, *sequences: str ) -> Self:
        return self.configure(stop=tuple(sequences))

    def json ( self, enabled: bool = True ) -> Self:
        return self.configure(json=enabled)

    def meta ( self, **metadata: Any ) -> Self:
        return self.configure(metadata={ **self._options.metadata, **metadata })

    def configure ( self, **changes: Any ) -> Self:

        self._options = self._options.merged(**changes)

        return self

    def attach ( self, *attachments: Attachment ) -> Self:

        self._files.extend(attachments)

        return self

    async def attach_path ( self, *paths: Path | str ) -> Self:

        for path in paths: self._files.append(await Attachment.from_path(path))

        return self

    def history ( self, messages: Sequence[Message] ) -> Self:

        self._history = list(messages)

        return self

    def session ( self, key: str | None = None ) -> Self:

        if key is None or not self._sessions.has(key):
            self._session = self._sessions.new(self._provider.name, self._options.model, self._options.system, key)
        else: self._session = self._sessions.resume(key)

        return self

    def resume ( self, key: str ) -> Self:

        self._session = self._sessions.resume(key)

        return self

    def current ( self ) -> Session | None:
        return self._session

    def session_id ( self ) -> str | None:
        return self._session.id if self._session else None

    def messages ( self, text: str ) -> list[Message]:

        asked = Message.user(text, *self._files)
        prior = self._session.history() if self._session else self._history

        return [*prior, asked]

    def settled ( self ) -> Options:

        if self._session is None: return self._options

        model  = self._options.model or self._session.model
        system = self._options.system or self._session.system

        return self._options.merged(model=model, system=system)

    async def ask ( self, text: str ) -> Reply:

        messages = self.messages(text)
        reply    = await self._provider.complete(messages, self.settled())

        self.remember(messages[-1], reply.text, reply.usage)

        log.info(
            "llm.replied", provider=self._provider.name, model=reply.model, tokens=reply.usage.total(), ms=reply.ms,
        )

        return reply

    async def stream ( self, text: str ) -> AsyncIterator[Chunk]:

        messages = self.messages(text)
        parts: list[str] = []
        usage = Usage()

        async for chunk in self._provider.stream(messages, self.settled()):

            if chunk.text: parts.append(chunk.text)
            if chunk.usage is not None: usage = chunk.usage

            yield chunk

        self.remember(messages[-1], "".join(parts), usage)

    def remember ( self, asked: Message, answer: str, usage: Usage ) -> None:

        self._files = []

        if self._session is None: return

        self._session.add(asked, Message.assistant(answer)).spent(usage)
        self._sessions.keep(self._session)

    def describe ( self ) -> dict[str, Any]:

        return {
            "provider": self._provider.name, "model": self._options.model or self._provider.model,
            "session": self.session_id(), "files": len(self._files), "history": len(self._history),
        }
