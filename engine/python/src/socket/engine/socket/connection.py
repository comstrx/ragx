from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from engine.date import date
from engine.error import Code, Fault
from engine.json import json
from starlette.websockets import WebSocketDisconnect, WebSocketState
import asyncio

EVENT    = 64
CHANNEL  = 128
COMMANDS = frozenset({"subscribe", "unsubscribe", "ping", "pong", "publish"})
PRESENCE   = "presence-"
PRIVATE    = "private-"
TOO_BIG    = 1009
POLICY     = 1008
GOING_AWAY = 1001
TRY_AGAIN  = 1013

@dataclass(frozen=True, slots=True)
class Frame:

    event   : str
    channel : str | None = None
    data    : Any = None
    id      : str | None = None

    def encode ( self ) -> bytes:

        body: dict[str, Any] = { "event": self.event }

        if self.channel is not None: body["channel"] = self.channel
        if self.data is not None: body["data"] = self.data
        if self.id is not None: body["id"] = self.id

        return json.encode(body)

    @classmethod
    def decode ( cls, raw: str | bytes ) -> Frame:

        body = json.parse(raw)

        if not isinstance(body, dict): raise Fault(Code.BAD_REQUEST, reason="frame")

        event   = body.get("event")
        channel = body.get("channel")
        ident   = body.get("id")

        if not isinstance(event, str) or not event or len(event) > EVENT:
            raise Fault(Code.BAD_REQUEST, reason="frame.event")
        if channel is not None and (not isinstance(channel, str) or len(channel) > CHANNEL):
            raise Fault(Code.BAD_REQUEST, reason="frame.channel")

        return cls(event, channel, body.get("data"), str(ident) if ident is not None else None)

    @classmethod
    def command ( cls, raw: str | bytes ) -> Frame:

        frame = cls.decode(raw)

        if frame.event not in COMMANDS: raise Fault(Code.BAD_REQUEST, reason="frame.command")

        return frame

    def reply ( self, event: str, data: Any = None ) -> Frame:

        return Frame(event, self.channel, data, self.id)

    def error ( self, fault: Fault ) -> Frame:

        return Frame("error", self.channel, { "code": fault.code, "reason": fault.reason }, self.id)

    def is_command ( self ) -> bool:

        return self.event in COMMANDS

    def auth ( self ) -> str | None:

        token = self.data.get("auth") if isinstance(self.data, dict) else None

        return token if isinstance(token, str) else None

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
