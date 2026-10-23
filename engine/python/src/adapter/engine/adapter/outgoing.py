from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, Self

from engine.error import Code, Fault

class Courier(Protocol):

    async def send ( self, item: Any, using: str | None = None ) -> Receipt: ...

    def prepare ( self, item: Any, using: str | None = None ) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class Piece:

    name    : str
    content : bytes
    type    : str = "application/octet-stream"

    def dump ( self ) -> dict[str, object]:

        return { "name": self.name, "type": self.type, "size": len(self.content) }

@dataclass(frozen=True, slots=True, kw_only=True)
class Receipt:

    provider : str
    id       : str
    status   : str
    to       : tuple[str, ...] = ()
    raw      : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def accepted ( self ) -> bool:

        return self.status in ("queued", "accepted", "sent", "delivered", "logged")

    def dump ( self ) -> dict[str, Any]:

        return { "provider": self.provider, "id": self.id, "status": self.status, "to": list(self.to) }

@dataclass(frozen=True, slots=True, kw_only=True)
class Outgoing:

    recipients  : tuple[str, ...] = ()
    sender      : str | None = None
    body        : str | None = None
    tags        : tuple[str, ...] = ()
    metadata    : Mapping[str, str] = field(default_factory=dict)
    attachments : tuple[Piece, ...] = ()
    provider    : str | None = None
    owner       : Courier | None = field(default=None, compare=False, repr=False)

    def to ( self, *recipients: str ) -> Self:

        return replace(self, recipients=(*self.recipients, *(item.strip() for item in recipients if item.strip())))

    def from_ ( self, sender: str ) -> Self:

        return replace(self, sender=sender)

    def text ( self, body: str ) -> Self:

        return replace(self, body=body)

    def tag ( self, *tags: str ) -> Self:

        return replace(self, tags=(*self.tags, *tags))

    def meta ( self, **values: str ) -> Self:

        return replace(self, metadata={ **self.metadata, **values })

    def attach ( self, name: str, content: bytes, kind: str = "application/octet-stream" ) -> Self:

        return replace(self, attachments=(*self.attachments, Piece(name, content, kind)))

    def via ( self, provider: str ) -> Self:

        return replace(self, provider=provider)

    def bound ( self, owner: Courier ) -> Self:

        return replace(self, owner=owner)

    def courier ( self ) -> Courier:

        if self.owner is None: raise Fault(Code.INTERNAL, reason=f"{type(self).__name__.lower()}.unbound")

        return self.owner

    async def send ( self ) -> Receipt:

        return await self.courier().send(self, self.provider)

    def prepare ( self ) -> dict[str, Any]:

        return self.courier().prepare(self, self.provider)

    def size ( self ) -> int:

        return len(self.body or "") + sum(len(item.content) for item in self.attachments)

    def shared ( self ) -> dict[str, Any]:

        return {
            "to": list(self.recipients), "sender": self.sender, "body": self.body, "tags": list(self.tags),
            "metadata": dict(self.metadata), "attachments": [item.dump() for item in self.attachments],
            "provider": self.provider,
        }
