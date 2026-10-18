from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol

from httpx import AsyncBaseTransport
from core.error import Code, Fault
from core.net import Client, Reply as Http, Sse
from .message import Chunk, Message, Options, Reply

UNAUTHORIZED = (401, 403)
RATE         = 429
CLIENT       = 400
SERVER       = 500

class Provider(Protocol):

    @property
    def name ( self ) -> str: ...

    @property
    def model ( self ) -> str: ...

    async def complete ( self, messages: Sequence[Message], options: Options ) -> Reply: ...

    def stream ( self, messages: Sequence[Message], options: Options ) -> AsyncIterator[Chunk]: ...

    async def models ( self ) -> list[str]: ...

    async def close ( self ) -> None: ...

class Remote:

    name  = "remote"
    model = ""

    def __init__ (
        self, base: str, key: str = "", model: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: AsyncBaseTransport | None = None,
    ) -> None:

        self._base   = base.rstrip("/")
        self._key    = key
        self._wait   = wait
        self._client = Client(self._base, {}, wait, retries, transport=transport)

        if model: self.model = model

    def headers ( self ) -> dict[str, str]:
        return { "authorization": f"Bearer {self._key}" } if self._key else {}

    def pick ( self, options: Options ) -> str:
        return options.model or self.model

    async def post ( self, path: str, body: Mapping[str, Any], wait: float | None = None ) -> Any:

        reply = await self._client.request("POST", path, json=body, headers=self.headers(), wait=wait or self._wait)

        self.guard(reply)

        return reply.json()

    async def get ( self, path: str ) -> Any:

        reply = await self._client.request("GET", path, headers=self.headers())

        self.guard(reply)

        return reply.json()

    def events ( self, path: str, body: Mapping[str, Any] ) -> AsyncIterator[Sse]:
        return self._client.sse("POST", path, body, self.headers(), self._wait)

    def guard ( self, reply: Http ) -> None:

        if reply.ok(): return

        reason = f"llm.{self.name}"

        if reply.status in UNAUTHORIZED: raise Fault(Code.UNAUTHORIZED, reason=f"{reason}.key")
        if reply.status == RATE: raise Fault(Code.TOO_MANY_REQUESTS, reason=f"{reason}.rate")
        if CLIENT <= reply.status < SERVER: raise Fault(Code.BAD_REQUEST, reason=f"{reason}.request")

        raise Fault(Code.UNAVAILABLE, reason=reason)

    async def models ( self ) -> list[str]:
        return [self.model]

    async def close ( self ) -> None:
        await self._client.close()

    def describe ( self ) -> dict[str, Any]:
        return { "name": self.name, "model": self.model, "base": self._base, "keyed": bool(self._key) }

def text_of ( value: object ) -> str:

    if isinstance(value, str): return value
    if isinstance(value, list):
        return "".join(str(part.get("text", "")) for part in value if isinstance(part, dict))

    return ""
