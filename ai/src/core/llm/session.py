from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from core.date import date
from core.error import Code, Fault
from core.fast import Ttl
from core.fs import Records
from core.rand import rand
from core.string import string
from .message import Message, Usage
from core.thread import Mutex

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
    name     : str = ""
    summary  : str = ""
    lock     : Mutex = field(default_factory=Mutex, repr=False)

    def add ( self, *messages: Message ) -> Session:

        self.messages.extend(messages)
        self.updated = date.stamp()

        return self

    def spent ( self, usage: Usage ) -> Session:

        self.usage = self.usage.plus(usage)
        self.turns += 1

        return self

    def history ( self, limit: int | None = None ) -> list[Message]:

        if limit is not None and limit < 0: raise Fault(Code.VALIDATION, reason="llm.session.limit")
        return list(self.messages) if limit is None else self.messages[-limit:] if limit else []

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "provider": self.provider, "model": self.model, "system": self.system,
            "messages": [message.dump() for message in self.messages], "usage": self.usage.dump(),
            "turns": self.turns, "created": self.created, "updated": self.updated, "name": self.name,
            "summary": self.summary,
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Session:

        return cls(
            id=str(data["id"]), provider=str(data["provider"]), model=data.get("model"), system=data.get("system"),
            messages=[Message.load(item) for item in data.get("messages", [])],
            usage=Usage(int(data["usage"]["input"]), int(data["usage"]["output"])),
            turns=int(data["turns"]), created=float(data["created"]), updated=float(data["updated"]),
            name=str(data.get("name", "")), summary=str(data.get("summary", "")),
        )

class Sessions:

    def __init__ ( self, ttl: float = HOUR, capacity: int = 10_000, path: str | None = None ) -> None:

        self._ttl = ttl
        self._store: Ttl[str, Session] = Ttl(limit=capacity)
        self._records = Records(path) if path else None

    def new (
        self, provider: str, model: str | None = None, system: str | None = None, key: str | None = None,
        history: Sequence[Message] = (), name: str = "conversation",
    ) -> Session:

        identifier = key or str(rand.uuid())
        if self.has(identifier): raise Fault(Code.CONFLICT, reason="llm.session.exists")
        session = Session(
            identifier, provider, model, system, list(history),
            name=f"{string.slug(name)[:48] or 'conversation'}-{identifier}",
        )
        self.keep(session)

        return session

    def resume ( self, key: str ) -> Session:

        found = self._store.get(key)
        if found is None: raise Fault(Code.NOT_FOUND, reason="llm.session")
        return found

    async def restore ( self, key: str ) -> Session:

        if self._records is not None:
            found = await self._records.read(key)
            if found is not None:
                session = Session.load(found)
                self.keep(session)
                return session
        return self.resume(key)

    @asynccontextmanager
    async def transaction ( self, key: str ) -> AsyncIterator[Session]:

        if self._records is not None:
            async with self._records.lock(key):
                yield await self.restore(key)
            return

        session = self.resume(key)
        async with session.lock: yield self.resume(key)

    async def save ( self, session: Session ) -> None:

        if self.has(session.id): session.lock = self.resume(session.id).lock
        if self._records is not None: await self._records.write(session.id, session.dump())
        self.keep(session)

    def keep ( self, session: Session ) -> Session:

        self._store.set(session.id, session, self._ttl)
        return session

    def has ( self, key: str ) -> bool:

        return self._store.has(key)

    def ids ( self ) -> list[str]:

        return self._store.keys()

    async def forget ( self, key: str ) -> bool:

        if self._records is not None:
            async with self._records.lock(key):
                deleted = await self._records.forget(key)
                return self._store.delete(key) or deleted
        return self._store.delete(key)

    def describe ( self ) -> dict[str, Any]:

        return {"sessions": len(self._store), "ttl": self._ttl, "durable": self._records is not None}
