from collections.abc import Mapping, Sequence

from core.http import Response


class BaseController:

    def ok (
        self, data: object = None, message: str | None = None, meta: Mapping[str, object] | None = None,
    ) -> Response:
        return Response.ok(data, message, meta)

    def created ( self, data: object = None, message: str | None = None ) -> Response:
        return Response.created(data, message)

    def accepted ( self, data: object = None, message: str | None = None ) -> Response:
        return Response.accepted(data, message)

    def page ( self, rows: Sequence[object], total: int, page: int = 1, limit: int = 20 ) -> Response:
        return Response.page(rows, total, page, limit)
