from collections.abc import AsyncIterator, Mapping, Sequence

from core.http import Packet, Response
from core.view import view

class Controller:

    def ok (
        self, data: object = None, message: str | None = None, meta: Mapping[str, object] | None = None,
    ) -> Response:

        return Response.ok(data, message, meta)

    def created ( self, data: object = None, message: str | None = None ) -> Response:

        return Response.created(data, message)

    def accepted ( self, data: object = None, message: str | None = None ) -> Response:

        return Response.accepted(data, message)

    def no_content ( self ) -> Response:

        return Response.no_content()

    def page ( self, rows: Sequence[object], total: int, page: int = 1, limit: int = 20 ) -> Response:

        return Response.page(rows, total, page, limit)

    def redirect ( self, url: str, status: int = 307 ) -> Response:

        return Response.redirect(url, status)

    def stream (
        self, chunks: AsyncIterator[bytes], media: str = "application/octet-stream", name: str | None = None,
    ) -> Response:

        return Response.stream(chunks, media, name)

    def sse ( self, source: AsyncIterator[Packet], ping: float = 15.0 ) -> Response:

        return Response.sse(source, ping)

    async def render ( self, name: str, status: int = 200, /, **data: object ) -> Response:

        return Response.html(await view.render(name, **data), status)
