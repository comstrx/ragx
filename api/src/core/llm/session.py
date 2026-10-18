from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.date import date
from core.error import Code, Fault
from core.fast import Ttl
from core.rand import rand
from .message import Message, Usage

HOUR = 3600.0

@dataclass(slots=True)
class Session:

    id       : str
    provider : str
    model    : str | None = None
    system   : str | None = None
    messages : list[Message] = field(default_factory=list)
    usage    : Usage = field(default_factory=Usage)
    turns    : int = 0
    created  : float = field(default_factory=date.stamp)
    updated  : float = field(default_factory=date.stamp)
    meta     : dict[str, Any] = field(default_factory=dict)

    def add ( self, *messages: Message ) -> Session:

        self.messages.extend(messages)
        self.updated = date.stamp()

        return self

    def spent ( self, usage: Usage ) -> Session:

        self.usage  = self.usage.plus(usage)
        self.turns += 1

        return self

    def history ( self, limit: int | None = None ) -> list[Message]:
        return self.messages[-limit:] if limit else list(self.messages)

    def last ( self ) -> Message | None:
        return self.messages[-1] if self.messages else None

    def trim ( self, keep: int ) -> int:

        dropped = max(len(self.messages) - keep, 0)

        if dropped: self.messages = self.messages[dropped:]

        return dropped

    def clear ( self ) -> Session:

        self.messages.clear()

        return self

    def age ( self ) -> float:
        return round(date.stamp() - self.created, 3)

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "provider": self.provider, "model": self.model, "system": self.system,
            "messages": [message.dump() for message in self.messages], "usage": self.usage.dump(),
            "turns": self.turns, "created": self.created, "updated": self.updated, "meta": self.meta,
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Session:

        return cls(
            str(data["id"]), str(data.get("provider", "")), data.get("model"), data.get("system"),
            [Message.load(item) for item in data.get("messages", [])],
            Usage(int(data.get("usage", {}).get("input", 0)), int(data.get("usage", {}).get("output", 0))),
            int(data.get("turns", 0)), float(data.get("created", date.stamp())),
            float(data.get("updated", date.stamp())),
            dict(data.get("meta", {})),
        )

class Sessions:

    def __init__ ( self, ttl: float = HOUR, capacity: int = 10_000 ) -> None:

        self._ttl   = ttl
        self._store: Ttl[str, Session] = Ttl(capacity)

    def new (
        self, provider: str, model: str | None = None, system: str | None = None, key: str | None = None,
        history: Sequence[Message] = (),
    ) -> Session:

        session = Session(key or str(rand.uuid()), provider, model, system, list(history))

        self._store.set(session.id, session, self._ttl)

        return session

    def get ( self, key: str ) -> Session | None:
        return self._store.get(key)

    def resume ( self, key: str ) -> Session:

        found = self._store.get(key)

        if found is None: raise Fault(Code.NOT_FOUND, reason=f"llm.session.{key}")

        self._store.touch(key, self._ttl)

        return found

    def keep ( self, session: Session ) -> Session:

        self._store.set(session.id, session, self._ttl)

        return session

    def forget ( self, key: str ) -> bool:
        return self._store.delete(key)

    def has ( self, key: str ) -> bool:
        return self._store.has(key)

    def ids ( self ) -> list[str]:
        return self._store.keys()

    def count ( self ) -> int:
        return len(self._store)

    def clear ( self ) -> None:
        self._store.clear()

    def describe ( self ) -> dict[str, Any]:
        return { "sessions": len(self._store), "ttl": self._ttl }
