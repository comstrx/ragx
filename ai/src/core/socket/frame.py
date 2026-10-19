from dataclasses import dataclass
from typing import Any

from core.error import Code, Fault
from core.json import json

EVENT    = 64
CHANNEL  = 128
COMMANDS = frozenset({"subscribe", "unsubscribe", "ping", "pong", "publish"})

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
