from contextvars import ContextVar, Token
from uuid import uuid7


class Context:

    def __init__ ( self ) -> None:

        self._request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

    def request_id ( self ) -> str | None:
        return self._request_id.get()

    def start ( self, request_id: str | None = None ) -> Token[str | None]:
        return self._request_id.set(request_id or str(uuid7()))

    def finish ( self, token: Token[str | None] ) -> None:
        self._request_id.reset(token)
