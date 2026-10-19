from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Any, Literal, Self, override

from starlette.responses import (
    FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response as Raw, StreamingResponse,
)
from core.array import array
from core.error import Code, Fault
from core.json import json
from .envelope import Envelope
from .sse import PING, EventStream, Packet

type Meta = Mapping[str, object] | None
type Headers = Mapping[str, str] | None

class Response(Raw):

    media_type: str | None = "application/json"

    @override
    def render ( self, content: object ) -> bytes:

        return json.encode(content)

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

        return cls(Envelope.failure(fault, meta), fault.status)

    @classmethod
    def problem ( cls, code: Code, reason: str | None = None, errors: Mapping[str, list[str]] | None = None ) -> Self:

        return cls.fail(Fault(code, reason=reason, errors=dict(errors) if errors else None))

    @classmethod
    def json ( cls, data: object, status: int = HTTPStatus.OK, headers: Headers = None ) -> Self:

        return cls(data, status, headers=dict(headers or {}))

    @classmethod
    def with_headers[R: Raw] ( cls, response: R, **headers: str ) -> R:

        for name, value in headers.items(): response.headers[name.replace("_", "-")] = value

        return response

    @staticmethod
    def with_cookie[R: Raw] (
        response: R, name: str, value: str, max_age: int | None = None, path: str = "/", secure: bool = True,
        http_only: bool = True, same_site: Literal["lax", "strict", "none"] = "lax",
    ) -> R:

        response.set_cookie(
            name, value, max_age=max_age, path=path, secure=secure, httponly=http_only, samesite=same_site,
        )

        return response

    @staticmethod
    def without_cookie[R: Raw] ( response: R, name: str, path: str = "/" ) -> R:

        response.delete_cookie(name, path=path)

        return response

    @staticmethod
    def stream_download (
        chunks: AsyncIterator[bytes], name: str, media: str = "application/octet-stream",
    ) -> StreamingResponse:

        return Response.stream(chunks, media, name, download=True)

    @staticmethod
    def no_content () -> Raw:

        return Raw(status_code=HTTPStatus.NO_CONTENT)

    @staticmethod
    def text ( content: str, status: int = HTTPStatus.OK, media: str = "text/plain" ) -> PlainTextResponse:

        return PlainTextResponse(content, status_code=status, media_type=media)

    @staticmethod
    def html ( content: str, status: int = HTTPStatus.OK ) -> HTMLResponse:

        return HTMLResponse(content, status_code=status)

    @staticmethod
    def raw ( content: bytes, media: str = "application/octet-stream", status: int = HTTPStatus.OK ) -> Raw:

        return Raw(content, status_code=status, media_type=media)

    @staticmethod
    def redirect ( url: str, status: int = HTTPStatus.TEMPORARY_REDIRECT, headers: Headers = None ) -> RedirectResponse:

        return RedirectResponse(url, status_code=status, headers=dict(headers or {}))

    @staticmethod
    def permanent_redirect ( url: str ) -> RedirectResponse:

        return RedirectResponse(url, status_code=HTTPStatus.PERMANENT_REDIRECT)

    @staticmethod
    def file ( path: Path, name: str | None = None, media: str | None = None, download: bool = False ) -> FileResponse:

        disposition = "attachment" if download else "inline"

        return FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition)

    @staticmethod
    def download ( path: Path, name: str | None = None, media: str | None = None ) -> FileResponse:

        return Response.file(path, name or path.name, media, download=True)

    @staticmethod
    def stream (
        chunks: AsyncIterator[bytes], media: str = "application/octet-stream", name: str | None = None,
        download: bool = False, headers: Headers = None,
    ) -> StreamingResponse:

        disposition = "attachment" if download else "inline"
        sent        = dict(headers or {})

        if name: sent["Content-Disposition"] = f'{disposition}; filename="{name}"'

        return StreamingResponse(chunks, media_type=media, headers=sent)

    @staticmethod
    def sse ( source: AsyncIterator[Packet], ping: float = PING, headers: Headers = None ) -> EventStream:

        return EventStream(source, ping, headers=headers)

    @staticmethod
    def ndjson ( items: AsyncIterator[Any] | Iterable[Any], headers: Headers = None ) -> StreamingResponse:

        async def lines () -> AsyncIterator[bytes]:

            if isinstance(items, AsyncIterator):
                async for item in items: yield json.encode(item) + b"\n"
            else:
                for item in items: yield json.encode(item) + b"\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson", headers=dict(headers or {}))
