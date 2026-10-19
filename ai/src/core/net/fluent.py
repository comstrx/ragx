from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from typing import Any, Self

from .breaker import Breaker, Hook, Hooks
from .reply import Reply
import base64

type Query = Mapping[str, object]

class Fluent(ABC):

    _headers : dict[str, str]
    _breaker : Breaker | None
    hooks    : Hooks

    @abstractmethod
    async def get (
        self, url: str, params: Query | None = None, headers: Mapping[str, str] | None = None,
        wait: float | None = None,
    ) -> Reply: ...

    def with_bearer ( self, token: str ) -> Self:

        self._headers["authorization"] = f"Bearer {token}"

        return self

    def with_basic ( self, user: str, password: str ) -> Self:

        self._headers["authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

        return self

    def with_header ( self, name: str, value: str ) -> Self:

        self._headers[name.lower()] = value

        return self

    def with_breaker ( self, breaker: Breaker ) -> Self:

        self._breaker = breaker

        return self

    def on_before ( self, hook: Hook ) -> Self:

        self.hooks.on_before(hook)

        return self

    def on_after ( self, hook: Hook ) -> Self:

        self.hooks.on_after(hook)

        return self

    def on_error ( self, hook: Hook ) -> Self:

        self.hooks.on_error(hook)

        return self

    def breaker ( self ) -> Breaker | None:

        return self._breaker

    async def pages (
        self, url: str, items: str = "data", following: str = "next", limit: int = 100, params: Query | None = None,
    ) -> AsyncIterator[Any]:

        target: str | None = url
        seen = 0

        while target and seen < limit:

            reply  = (await self.get(target, params if seen == 0 else None)).raise_for_status()
            body   = reply.json()
            found  = body.get(items, []) if isinstance(body, dict) else body
            target = body.get(following) if isinstance(body, dict) else None
            seen  += 1

            for item in found or []: yield item
