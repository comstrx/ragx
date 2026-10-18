from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.websockets import WebSocketDisconnect, WebSocketState
from core.date import date
from .frame import Frame
import asyncio

PRESENCE   = "presence-"
PRIVATE    = "private-"
TOO_BIG    = 1009
POLICY     = 1008
GOING_AWAY = 1001
TRY_AGAIN  = 1013

class Transport(Protocol):

    @property
    def client_state ( self ) -> WebSocketState: ...

    async def send_bytes ( self, data: bytes ) -> None: ...

    async def receive ( self ) -> Mapping[str, Any]: ...

    async def close ( self, code: int = 1000, reason: str | None = None ) -> None: ...

@dataclass(frozen=True, slots=True)
class Grant:

    allowed : bool = False
    member  : Mapping[str, Any] | None = None
    publish : bool = False
    reason  : str | None = None

@dataclass(slots=True)
class Limits:

    connections : int = 10_000
    queue       : int = 256
    frame       : int = 64 * 1024
    ping        : float = 25.0
    drops       : int = 64

@dataclass(slots=True)
class Connection:

    id       : str
    socket   : Transport
    token    : str | None = None
    user     : Any = None
    channels : dict[str, Grant] = field(default_factory=dict)
    outbox   : asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    opened   : float = field(default_factory=date.stamp)
    sent     : int = 0
    received : int = 0
    dropped  : int = 0
    closed   : bool = False
    writer   : asyncio.Task[None] | None = None
    meta     : dict[str, Any] = field(default_factory=dict)

    def offer ( self, data: bytes ) -> bool:

        if self.closed: return False

        try: self.outbox.put_nowait(data)
        except asyncio.QueueFull:

            self.dropped += 1

            return False

        return True

    def emit ( self, event: str, data: Any = None, channel: str | None = None ) -> bool:
        return self.offer(Frame(event, channel, data).encode())

    async def pump ( self ) -> None:

        while not self.closed:

            data = await self.outbox.get()

            if self.socket.client_state != WebSocketState.CONNECTED: break

            try: await self.socket.send_bytes(data)
            except (WebSocketDisconnect, RuntimeError, OSError): break

            self.sent += 1

        self.closed = True

    async def close ( self, code: int = GOING_AWAY, reason: str = "" ) -> None:

        if self.closed: return

        self.closed = True

        if self.writer is not None: self.writer.cancel()
        if self.socket.client_state == WebSocketState.CONNECTED: await self.socket.close(code, reason)

    def subscribed ( self, channel: str ) -> bool:
        return channel in self.channels

    def presence ( self ) -> list[str]:
        return [name for name in self.channels if name.startswith(PRESENCE)]

    def user_id ( self ) -> str | None:

        found = getattr(self.user, "id", None)

        return str(found) if found is not None else None

    def age ( self ) -> float:
        return round(date.stamp() - self.opened, 3)

    def describe ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "user": self.user_id(), "channels": sorted(self.channels), "sent": self.sent,
            "received": self.received, "dropped": self.dropped, "age": self.age(), "closed": self.closed,
        }
