from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from engine.context import context
from engine.error import Code, Fault
from engine.net import net
from starlette.datastructures import UploadFile
from starlette.requests import Request as Raw

JSON    = "application/json"
PRIVATE = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")
type Payload = dict[str, object]
CHUNK = 64 * 1024

class Wire:

    def __init__ ( self, request: Raw ) -> None:

        self._request = request

    def header ( self, name: str, default: str = "" ) -> str:

        return self._request.headers.get(name, default)

    def headers ( self ) -> dict[str, str]:

        return dict(self._request.headers)

    def bearer ( self ) -> str | None:

        scheme, _, token = self.header("authorization").partition(" ")

        return token.strip() or None if scheme.lower() == "bearer" else None

    def ip ( self, trusted: Sequence[str] | None = None ) -> str:

        peer    = self._request.client.host if self._request.client else ""
        proxies = self.shared("proxies", PRIVATE) if trusted is None else trusted

        return net.client_ip(self.header("x-forwarded-for"), peer, proxies)

    def method ( self ) -> str:

        return self._request.method

    def path ( self ) -> str:

        return self._request.url.path

    def url ( self ) -> str:

        return str(self._request.url)

    def route_name ( self ) -> str | None:

        route = self._request.scope.get("route")

        return getattr(route, "name", None) if route is not None else None

    def is_json ( self ) -> bool:

        return self.header("content-type").split(";")[0].strip().lower() == JSON

    def wants_json ( self ) -> bool:

        return JSON in self.header("accept", "*/*") or "*/*" in self.header("accept", "*/*")

    def accepts ( self, *kinds: str ) -> bool:

        accepted = self.header("accept", "*/*")

        return "*/*" in accepted or any(kind in accepted for kind in kinds)

    def is_secure ( self ) -> bool:

        return self._request.url.scheme == "https" or self.header("x-forwarded-proto") == "https"

    def is_method ( self, *methods: str ) -> bool:

        return self._request.method in { method.upper() for method in methods }

    def user ( self ) -> Any:

        return getattr(self._request.state, "user", None)

    def state ( self, key: str, default: object = None ) -> Any:

        return getattr(self._request.state, key, default)

    def assign ( self, **values: object ) -> None:

        for key, value in values.items(): setattr(self._request.state, key, value)

    def shared ( self, key: str, default: object = None ) -> Any:

        return getattr(self._request.app.state, key, default)

    def cookie ( self, name: str, default: str | None = None ) -> str | None:

        return self._request.cookies.get(name, default)

    def cookies ( self ) -> dict[str, str]:

        return dict(self._request.cookies)

    def host ( self ) -> str:

        return self._request.url.hostname or ""

    def user_agent ( self ) -> str:

        return self.header("user-agent")

    def ips ( self ) -> list[str]:

        hops = [hop.strip() for hop in self.header("x-forwarded-for").split(",") if hop.strip()]
        peer = self._request.client.host if self._request.client else ""

        return [*hops, *([peer] if peer else [])]

    def is_ ( self, *patterns: str ) -> bool:

        return any(fnmatch(self.path().strip("/"), pattern.strip("/")) for pattern in patterns)

    def route_is ( self, *patterns: str ) -> bool:

        name = self.route_name() or ""

        return any(fnmatch(name, pattern) for pattern in patterns)

@dataclass(frozen=True, slots=True)
class Inject:

    using : Any

class Upload:

    __slots__ = ("_file",)

    def __init__ ( self, file: UploadFile ) -> None:

        self._file = file

    @property
    def filename ( self ) -> str | None:

        return self._file.filename

    @property
    def content_type ( self ) -> str | None:

        return self._file.content_type

    @property
    def size ( self ) -> int | None:

        return self._file.size

    async def read ( self, size: int = -1 ) -> bytes:

        return await self._file.read(size)

    async def chunks ( self, size: int = CHUNK ) -> AsyncIterator[bytes]:

        await self._file.seek(0)

        while chunk := await self._file.read(size): yield chunk

    async def rewind ( self ) -> None:

        await self._file.seek(0)

    async def close ( self ) -> None:

        await self._file.close()

    def describe ( self ) -> dict[str, object]:

        return { "name": self.filename, "mime": self.content_type, "size": self.size }

class Envelope:

    @staticmethod
    def success (
        data: object = None, message: str | None = None,
        code: Code = Code.OK, meta: Mapping[str, object] | None = None,
    ) -> Payload:

        return Envelope.build(data, message, None, code, None, meta)

    @staticmethod
    def failure ( fault: Fault, meta: Mapping[str, object] | None = None ) -> Payload:

        return Envelope.build(None, fault.message, fault.errors, fault.code, fault.reason, meta)

    @staticmethod
    def build (
        data: object, message: str | None, errors: Mapping[str, list[str]] | None,
        code: Code, reason: str | None, meta: Mapping[str, object] | None,
    ) -> Payload:

        return {
            "data"    : data,
            "message" : message,
            "errors"  : dict(errors) if errors else None,
            "code"    : code,
            "reason"  : reason,
            "meta"    : { "request_id": context.request_id(), **(meta or {}) },
        }
