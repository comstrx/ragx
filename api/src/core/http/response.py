from collections.abc import AsyncIterator, Mapping, Sequence
from http import HTTPStatus
from pathlib import Path
from typing import Self

from starlette.responses import FileResponse, HTMLResponse, Response as Raw, StreamingResponse
from core.array import array
from core.exceptions import Code, Fault
from core.json import json
from .envelope import Envelope

type Meta = Mapping[str, object] | None

class Response(Raw):

    media_type = "application/json"

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

    @staticmethod
    def html ( content: str, status: int = HTTPStatus.OK ) -> HTMLResponse:
        return HTMLResponse(content, status_code=status)

    @staticmethod
    def file ( path: Path, name: str | None = None, media: str | None = None, download: bool = False ) -> FileResponse:

        disposition = "attachment" if download else "inline"

        return FileResponse(path, media_type=media, filename=name, content_disposition_type=disposition)

    @staticmethod
    def stream (
        chunks: AsyncIterator[bytes], media: str = "application/octet-stream", name: str | None = None,
    ) -> StreamingResponse:

        headers = { "Content-Disposition": f'inline; filename="{name}"' } if name else None

        return StreamingResponse(chunks, media_type=media, headers=headers)
