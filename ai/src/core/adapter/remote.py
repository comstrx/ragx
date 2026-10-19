from collections.abc import Mapping
from typing import Any, ClassVar, TypedDict, Unpack, override

from core.error import Code, Fault
from core.net import Client, Reply, Transport
from .adapter import Adapter

type Files = Mapping[str, tuple[str, bytes, str]]

class Payload(TypedDict, total=False):

    json    : object
    data    : Mapping[str, object] | None
    params  : Mapping[str, object] | None
    files   : Files | None
    headers : Mapping[str, str] | None
    key     : str | None

UNAUTHORIZED = (401, 403)
MISSING      = 404
CONFLICT     = 409
RATE         = 429
CLIENT       = 400
SERVER       = 500
KEYS         = ("message", "error_description", "detail", "description", "title", "error")

def message_of ( payload: object ) -> str | None:

    if isinstance(payload, str): return payload or None
    if isinstance(payload, list): return next((found for item in payload if (found := message_of(item))), None)
    if not isinstance(payload, Mapping): return None

    for key in KEYS:

        found = message_of(payload.get(key))

        if found: return found

    return message_of(payload.get("errors"))

class Remote(Adapter):

    idempotency : ClassVar[str] = "idempotency-key"

    def __init__ (
        self, base: str, wait: float = 20.0, retries: int = 2, transport: Transport | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:

        self._base   = base.rstrip("/")
        self._client = Client(self._base, dict(headers or {}), wait, retries, transport=transport)

    def headers ( self ) -> dict[str, str]:

        return {}

    async def send ( self, method: str, path: str, action: str, **options: Unpack[Payload] ) -> Reply:

        key  = options.get("key")
        sent = { **self.headers(), **(options.get("headers") or {}) }

        if key: sent[type(self).idempotency] = key

        try:
            reply = await self._client.request(
                method, path, json=options.get("json"), data=options.get("data"), params=options.get("params"),
                files=options.get("files"), headers=sent,
            )
        except Fault as fault: raise fault.copy(reason=self.reason(f"{action}.{fault.reason}")) from fault

        self.guard(reply, action)

        return reply

    async def call ( self, method: str, path: str, action: str, **options: Unpack[Payload] ) -> Any:

        reply = await self.send(method, path, action, **options)

        return reply.json() if reply.body and reply.is_json() else {}

    def guard ( self, reply: Reply, action: str ) -> None:

        if reply.ok(): return

        message = self.message(reply)
        retry   = reply.header("retry-after")
        pause   = float(retry) if retry.isdigit() else None

        if reply.status in UNAUTHORIZED: raise self.fault(Code.UNAUTHORIZED, f"{action}.key", message)
        if reply.status == MISSING: raise self.fault(Code.NOT_FOUND, action, message)
        if reply.status == CONFLICT: raise self.fault(Code.CONFLICT, action, message)
        if reply.status == RATE: raise self.fault(Code.TOO_MANY_REQUESTS, f"{action}.rate", message, pause)
        if CLIENT <= reply.status < SERVER: raise self.fault(Code.BAD_REQUEST, f"{action}.request", message)

        raise self.fault(Code.UNAVAILABLE, action, None, pause)

    def message ( self, reply: Reply ) -> str | None:

        try: payload = reply.json() if reply.is_json() else reply.text()
        except Fault: payload = reply.text()

        found = message_of(payload)

        return found[:300] if found else None

    @override
    async def close ( self ) -> None:

        await self._client.close()

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "base": self._base }
