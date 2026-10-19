from collections.abc import Awaitable, Callable

from fastapi import Request
from core.cache import cache
from core.error import Code, Fault
from core.parse import parse

type Keyed = Callable[[Request], str]

def by_client ( request: Request ) -> str:

    forwarded = request.headers.get("x-forwarded-for", "")
    client    = request.client.host if request.client else "anonymous"

    return (forwarded.split(",")[0].strip() or client) if forwarded else client

class Throttle:

    def parse ( self, rate: str ) -> tuple[int, float]:

        return parse.rate(rate)

    def guard ( self, rate: str, key: Keyed = by_client, scope: str = "" ) -> Callable[[Request], Awaitable[None]]:

        limit, window = self.parse(rate)

        async def limited ( request: Request ) -> None:

            bucket = f"throttle:{scope or request.url.path}:{key(request)}"
            hit    = await cache.hit(bucket, limit, window)

            request.state.throttle = { "limit": limit, "remaining": hit.remaining, "reset": round(hit.reset, 1) }

            if not hit.allowed: raise Fault(Code.TOO_MANY_REQUESTS, reason=f"retry in {round(hit.reset)}s")

        limited.__name__ = f"throttle_{limit}_per_{int(window)}s"

        return limited
