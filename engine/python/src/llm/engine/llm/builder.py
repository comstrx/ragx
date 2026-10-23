from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self, Unpack

from engine.json import Schema
from engine.rand import rand
from .harness import Harness, Memory
from .message import Attachment, Effort, Message, Options, Tuning
from .provider import Provider
from .session import Session, Sessions
import copy

class Builder:

    def __init__ (
        self, provider: Provider, sessions: Sessions, harness: Harness | None = None, memory: Memory | None = None,
        summarizer: Provider | None = None,
    ) -> None:

        self._provider   = provider
        self._sessions   = sessions
        self._harness    = harness or Harness()
        self._memory     = memory or Memory()
        self._summarizer = summarizer
        self._options    = provider.spec.options
        self._files    : tuple[Attachment, ...] = ()
        self._history  : tuple[Message, ...] = ()
        self._key      : str | None = None
        self._fresh    = True
        self._grounding: str | None = None

    def provider ( self ) -> Provider:

        return self._provider

    def options ( self ) -> Options:

        return self._options

    def policy ( self ) -> Harness:

        return self._harness

    def derive ( self, **fields: object ) -> Self:

        made = copy.copy(self)

        for name, value in fields.items(): setattr(made, f"_{name}", value)

        return made

    def configure ( self, **changes: Unpack[Tuning] ) -> Self:

        return self.derive(options=self._options.merged(**changes))

    def model ( self, name: str ) -> Self:

        return self.configure(model=name)

    def system ( self, text: str ) -> Self:

        return self.configure(system=text)

    def instruct ( self, text: str ) -> Self:

        return self.configure(system="\n\n".join(filter(None, (self._options.system, text))))

    def temperature ( self, value: float ) -> Self:

        return self.configure(temperature=value)

    def max_tokens ( self, count: int ) -> Self:

        return self.configure(max_tokens=count)

    def top_p ( self, value: float ) -> Self:

        return self.configure(top_p=value)

    def top_k ( self, count: int ) -> Self:

        return self.configure(top_k=count)

    def stop ( self, *sequences: str ) -> Self:

        return self.configure(stop=tuple(sequences))

    def seed ( self, value: int ) -> Self:

        return self.configure(seed=value)

    def penalize ( self, presence: float | None = None, frequency: float | None = None ) -> Self:

        return self.configure(presence=presence, frequency=frequency)

    def effort ( self, level: Effort ) -> Self:

        return self.configure(effort=level)

    def extra ( self, **fields: Any ) -> Self:

        return self.configure(extra={ **self._options.extra, **fields })

    def json ( self, enabled: bool = True ) -> Self:

        return self.configure(json=enabled)

    def meta ( self, **metadata: Any ) -> Self:

        return self.configure(metadata={ **self._options.metadata, **metadata })

    def schema ( self, shape: Schema, native: bool = True ) -> Self:

        return self.configure(schema=shape, native=native)

    def ground ( self, sources: str | None ) -> Self:

        return self.derive(grounding=sources or None)

    def harness ( self, policy: Harness ) -> Self:

        return self.derive(harness=self._harness.merge(policy))

    def memory ( self, policy: Memory ) -> Self:

        return self.derive(memory=policy)

    def attach ( self, *attachments: Attachment ) -> Self:

        return self.derive(files=(*self._files, *attachments))

    async def attach_path ( self, *paths: Path | str ) -> Self:

        return self.attach(*[await Attachment.from_path(path) for path in paths])

    def history ( self, messages: Sequence[Message] ) -> Self:

        return self.derive(history=tuple(messages))

    def session ( self, key: str | None = None ) -> Self:

        return self.derive(key=key or str(rand.uuid()), fresh=True)

    def resume ( self, key: str ) -> Self:

        return self.derive(key=key, fresh=False)

    def session_id ( self ) -> str | None:

        return self._key

    def current ( self ) -> Session | None:

        return self._sessions.get(self._key) if self._key else None

    def chosen ( self ) -> str:

        return self._provider.pick(self._options)

    def bound ( self ) -> bool:

        return bool(self._files or self._history or self._key)

    def describe ( self ) -> dict[str, Any]:

        return {
            "provider": self._provider.name, "model": self._options.model or self._provider.model,
            "session": self._key, "files": len(self._files), "history": len(self._history),
            "schema": self._options.schema is not None, "native": self._options.native,
        }
