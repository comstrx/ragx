from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal, Self, override

from core.array import array
from core.error import Code, Fault
from core.json import json
from starlette.responses import FileResponse, RedirectResponse, Response as Raw, StreamingResponse
from starlette.types import Receive, Scope, Send
from .wire import Envelope
import asyncio, math

type Packet = Sse | Mapping[str, Any] | str | bytes

HEADERS = { "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive" }
PING    = 15.0
type Meta = Mapping[str, object] | None
type Headers = Mapping[str, str] | None
type SameSite = Literal["lax", "strict", "none"]
JSON   = "application/json"
BINARY = "application/octet-stream"

@dataclass(frozen=True, slots=True)
class Sse:

    data  : Any
    event : str | None = None
    id    : str | None = None
    retry : int | None = None

    def encode ( self ) -> bytes:

        lines: list[str] = []

        if self.event: lines.append(f"event: {self.event}")
        if self.id: lines.append(f"id: {self.id}")
        if self.retry: lines.append(f"retry: {int(self.retry)}")

        text = self.data if isinstance(self.data, str) else json.dumps(self.data)

        lines.extend(f"data: {line}" for line in text.split("\n"))

        return ("\n".join(lines) + "\n\n").encode()

    @staticmethod
    def comment ( text: str = "ping" ) -> bytes:

        return f": {text}\n\n".encode()

    @staticmethod
    def pack ( packet: Packet ) -> bytes:

        if isinstance(packet, Sse): return packet.encode()
        if isinstance(packet, bytes): return packet
        if isinstance(packet, str): return Sse(packet).encode()

        return Sse(
            packet.get("data"), packet.get("event"), packet.get("id"), packet.get("retry"),
        ).encode() if "data" in packet else Sse(dict(packet)).encode()

class EventStream(StreamingResponse):

    def __init__ (
        self, source: AsyncIterator[Packet], ping: float = PING, status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:

        super().__init__(
            self.pulse(source, ping), status_code=status, media_type="text/event-stream",
            headers={ **HEADERS, **(headers or {}) },
        )

    @staticmethod
    async def pulse ( source: AsyncIterator[Packet], ping: float ) -> AsyncIterator[bytes]:

        iterator = source.__aiter__()

        while True:

            try:
                async with asyncio.timeout(ping if ping > 0 else None): packet = await iterator.__anext__()
            except TimeoutError:

                yield Sse.comment()

                continue

            except StopAsyncIteration: return

            yield Sse.pack(packet)

class Response(Raw):

    media_type: str | None = JSON

    def __init__ (
        self, content: object = None, status_code: int = HTTPStatus.OK, headers: Headers = None,
        media: str | None = JSON,
    ) -> None:

        self._inner: Raw | None = None
        self.media_type         = media

        super().__init__(content, status_code, dict(headers or {}), media)

    @override
    def render ( self, content: object ) -> bytes:

        if isinstance(content, bytes): return content
        if isinstance(content, str): return content.encode(self.charset)
        if content is None and self.media_type != JSON: return b""

        return json.encode(content)

    @classmethod
    def _delegate_ ( cls, inner: Raw ) -> Self:

        made = cls(None, inner.status_code, media=inner.media_type)

        made.raw_headers = inner.raw_headers
        made._inner      = inner

        return made

    @override
    async def __call__ ( self, scope: Scope, receive: Receive, send: Send ) -> None:

        if self._inner is None: return await super().__call__(scope, receive, send)

        return await self._inner(scope, receive, send)

    def header ( self, name: str, value: str ) -> Self:

        self.headers[name] = value

        return self

    def cookie (
        self, name: str, value: str, max_age: int | None = None, path: str = "/", secure: bool = True,
        http_only: bool = True, same_site: SameSite = "lax",
    ) -> Self:

        self.set_cookie(name, value, max_age=max_age, path=path, secure=secure, httponly=http_only, samesite=same_site)

        return self

    def forget ( self, name: str, path: str = "/" ) -> Self:

        self.delete_cookie(name, path=path)

        return self

    def status ( self ) -> int:

        return self.status_code

    @classmethod
    def ok ( cls, data: object = None, message: str | None = None, meta: Meta = None ) -> Self:

        return cls(Envelope.success(data, message, Code.OK, meta), HTTPStatus.OK)

    @classmethod
    def created ( cls, data: object = None, message: str | None = None, meta: Meta = None ) -> Self:

        return cls(Envelope.success(data, message, Code.CREATED, meta), HTTPStatus.CREATED)

    @classmethod
    def accepted ( cls, data: object = None, message: str | None = None, meta: Meta = None ) -> Self:

        return cls(Envelope.success(data, message, Code.ACCEPTED, meta), HTTPStatus.ACCEPTED)

    @classmethod
    def page ( cls, rows: Sequence[object], total: int, page: int = 1, limit: int = 20, meta: Meta = None ) -> Self:

        return cls.ok(list(rows), meta={ **array.page(total, page, limit), **(meta or {}) })

    @classmethod
    def fail ( cls, fault: Fault, meta: Meta = None ) -> Self:

        made = cls(Envelope.failure(fault, meta), fault.status)

        if fault.retry_after is not None: made.headers["Retry-After"] = str(math.ceil(fault.retry_after))

        return made

    @classmethod
    def problem ( cls, code: Code, reason: str | None = None, errors: Mapping[str, list[str]] | None = None ) -> Self:

        return cls.fail(Fault(code, reason=reason, errors=dict(errors) if errors else None))

    @classmethod
    def json ( cls, data: object, status: int = HTTPStatus.OK, headers: Headers = None ) -> Self:

        return cls(data, status, headers)

    @classmethod
    def no_content ( cls ) -> Self:

        return cls(None, HTTPStatus.NO_CONTENT, media=None)

    @classmethod
    def text ( cls, content: str, status: int = HTTPStatus.OK, media: str = "text/plain" ) -> Self:

        return cls(content, status, media=media)

    @classmethod
    def html ( cls, content: str, status: int = HTTPStatus.OK ) -> Self:

        return cls(content, status, media="text/html")

    @classmethod
    def raw ( cls, content: bytes, media: str = BINARY, status: int = HTTPStatus.OK ) -> Self:

        return cls(content, status, media=media)

    @classmethod
    def redirect ( cls, url: str, status: int = HTTPStatus.TEMPORARY_REDIRECT, headers: Headers = None ) -> Self:

        return cls._delegate_(RedirectResponse(url, status_code=status, headers=dict(headers or {})))

    @classmethod
    def permanent_redirect ( cls, url: str ) -> Self:

        return cls.redirect(url, HTTPStatus.PERMANENT_REDIRECT)

    @classmethod
    def file ( cls, path: Path, name: str | None = None, media: str | None = None, download: bool = False ) -> Self:

        disposition = "attachment" if download else "inline"

        return cls._delegate_(FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition))

    @classmethod
    def download ( cls, path: Path, name: str | None = None, media: str | None = None ) -> Self:

        return cls.file(path, name or path.name, media, download=True)

    @classmethod
    def stream (
        cls, chunks: AsyncIterator[bytes], media: str = BINARY, name: str | None = None, download: bool = False,
        headers: Headers = None,
    ) -> Self:

        disposition = "attachment" if download else "inline"
        sent        = dict(headers or {})

        if name: sent["Content-Disposition"] = f'{disposition}; filename="{name}"'

        return cls._delegate_(StreamingResponse(chunks, media_type=media, headers=sent))

    @classmethod
    def sse ( cls, source: AsyncIterator[Packet], ping: float = PING, headers: Headers = None ) -> Self:

        return cls._delegate_(EventStream(source, ping, headers=headers))

    @classmethod
    def ndjson ( cls, items: AsyncIterator[Any] | Iterable[Any], headers: Headers = None ) -> Self:

        async def lines () -> AsyncIterator[bytes]:

            if isinstance(items, AsyncIterator):
                async for item in items: yield json.encode(item) + b"\n"
            else:
                for item in items: yield json.encode(item) + b"\n"

        streamed = StreamingResponse(lines(), media_type="application/x-ndjson", headers=dict(headers or {}))

        return cls._delegate_(streamed)
