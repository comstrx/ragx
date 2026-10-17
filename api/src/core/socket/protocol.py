from dataclasses import dataclass
from typing import Any

from core.exceptions import Code, Fault
from core.json import json

EVENT   = 64
CHANNEL = 128

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

    def reply ( self, event: str, data: Any = None ) -> Frame:
        return Frame(event, self.channel, data, self.id)
