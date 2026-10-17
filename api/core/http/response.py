from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Self

from starlette.responses import Response as Raw
from core.array import array
from core.error import Code, Fault
from .envelope import Envelope
import orjson

type Meta = Mapping[str, object] | None


class Response(Raw):

    media_type = "application/json"

    def render ( self, content: object ) -> bytes:
        return orjson.dumps(content)

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
