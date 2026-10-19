from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.date import date
from core.error import Code, Fault
from core.fast import Ttl
from core.rand import rand
from core.thread import Lane
from .message import Message, Usage

HOUR = 3600.0

class Ledger(Protocol):

    async def read ( self, key: str ) -> tuple[dict[str, Any], int] | None: ...

    async def write ( self, key: str, data: Mapping[str, Any], version: int ) -> bool: ...

    async def delete ( self, key: str ) -> bool: ...

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
    summary  : str = ""
    version  : int = 0
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

    def age ( self ) -> float:

        return round(date.stamp() - self.created, 3)

    def copy ( self ) -> Session:

        return Session.load(self.dump(), self.version)

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "provider": self.provider, "model": self.model, "system": self.system,
            "messages": [message.dump() for message in self.messages], "usage": self.usage.dump(),
            "turns": self.turns, "created": self.created, "updated": self.updated, "summary": self.summary,
            "meta": self.meta,
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any], version: int = 0 ) -> Session:

        spent = data.get("usage", {})

        return cls(
            str(data["id"]), str(data.get("provider", "")), data.get("model"), data.get("system"),
            [Message.load(item) for item in data.get("messages", [])],
            Usage(int(spent.get("input", 0)), int(spent.get("output", 0))), int(data.get("turns", 0)),
            float(data.get("created", date.stamp())), float(data.get("updated", date.stamp())),
            str(data.get("summary", "")), version, dict(data.get("meta", {})),
        )

class Sessions:

    def __init__ ( self, ttl: float = HOUR, capacity: int = 10_000, ledger: Ledger | None = None ) -> None:

        self._ttl    = ttl
        self._store: Ttl[str, Session] = Ttl(limit=capacity)
        self._ledger = ledger
        self._lanes: dict[str, tuple[Lane, int]] = {}

    def durable ( self ) -> bool:

        return self._ledger is not None

    def new (
        self, provider: str, model: str | None = None, system: str | None = None, key: str | None = None,
        history: Sequence[Message] = (),
    ) -> Session:

        return self.keep(Session(key or str(rand.uuid()), provider, model, system, list(history)))

    def get ( self, key: str ) -> Session | None:

        return self._store.get(key)

    def resume ( self, key: str ) -> Session:

        found = self._store.get(key)

        if found is None: raise Fault(Code.NOT_FOUND, reason="llm.session.missing")

        self._store.touch(key, self._ttl)

        return found

    async def restore ( self, key: str ) -> Session | None:

        if self._ledger is None: return self._store.get(key)

        found = await self._ledger.read(key)

        return self.keep(Session.load(*found)) if found is not None else None

    @asynccontextmanager
    async def transaction ( self, key: str, create: Callable[[], Session] ) -> AsyncIterator[Session]:

        lane, holders    = self._lanes.get(key, (Lane(1), 0))
        self._lanes[key] = (lane, holders + 1)

        try:

            async with lane.slot():

                found = await self.restore(key)

                yield (found or create()).copy()

        finally:

            lane, holders = self._lanes[key]

            if holders <= 1: self._lanes.pop(key, None)
            else: self._lanes[key] = (lane, holders - 1)

    async def save ( self, session: Session ) -> Session:

        if self._ledger is not None and not await self._ledger.write(session.id, session.dump(), session.version):
            raise Fault(Code.CONFLICT, reason="llm.session.conflict")

        session.version += 1

        return self.keep(session)

    def keep ( self, session: Session ) -> Session:

        self._store.set(session.id, session, self._ttl)

        return session

    async def forget ( self, key: str ) -> bool:

        gone = self._store.delete(key)

        return await self._ledger.delete(key) or gone if self._ledger is not None else gone

    def has ( self, key: str ) -> bool:

        return self._store.has(key)

    def ids ( self ) -> list[str]:

        return self._store.keys()

    def count ( self ) -> int:

        return len(self._store)

    def clear ( self ) -> int:

        return self._store.clear()

    def describe ( self ) -> dict[str, Any]:

        return { "sessions": len(self._store), "ttl": self._ttl, "durable": self.durable() }
