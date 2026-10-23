from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from engine.cache import cache
from engine.error import Code, Fault
from engine.parse import parse
from fastapi import FastAPI
from .request import Request
from .route import Bound, Group
from .wire import PRIVATE
import re

PARAM = re.compile(r"\{(\w+)(?::\w+)?\}")
type Known = Mapping[str, object]
type Keyed = Callable[[Request], str]

class Router:

    def __init__ ( self ) -> None:

        self._bound: list[Bound] = []
        self._named: dict[str, Bound] = {}

    def register ( self, group: Group ) -> int:

        added = 0

        for bound in group.walk():

            self._bound.append(bound)

            if bound.name: self._named[bound.name] = bound

            added += 1

        return added

    def has ( self, name: str ) -> bool:

        return name in self._named

    def find ( self, name: str ) -> Bound:

        found = self._named.get(name)

        if found is None: raise Fault(Code.NOT_FOUND, reason=f"route.{name}")

        return found

    def url ( self, name: str, **params: object ) -> str:

        bound = self.find(name)
        left  = dict(params)

        def fill ( match: re.Match[str] ) -> str:

            key = match.group(1)

            if key not in left: raise Fault(Code.INTERNAL, reason=f"route.{name}.{key}")

            return str(left.pop(key))

        path  = PARAM.sub(fill, bound.path)
        query = urlencode({ key: str(value) for key, value in left.items() if value is not None })

        return f"{path}?{query}" if query else path

    def params ( self, name: str ) -> list[str]:

        return PARAM.findall(self.find(name).path)

    def names ( self ) -> list[str]:

        return [bound.name for bound in self._bound if bound.name]

    def routes ( self ) -> list[Bound]:

        return list(self._bound)

    def by_tag ( self, tag: str ) -> list[Bound]:

        return [bound for bound in self._bound if tag in bound.tags]

    def by_prefix ( self, prefix: str ) -> list[Bound]:

        return [bound for bound in self._bound if bound.path.startswith(prefix)]

    def methods ( self, path: str ) -> list[str]:

        return sorted({ method for bound in self._bound if bound.path == path for method in bound.methods })

    def clear ( self ) -> None:

        self._bound.clear()
        self._named.clear()

    def describe ( self ) -> list[dict[str, Any]]:

        return [
            {
                "path": bound.path, "methods": list(bound.methods), "name": bound.name, "tags": list(bound.tags),
                "guards": len(bound.middleware), "throttle": bound.throttle,
            }
            for bound in self._bound
        ]

def keep ( engine: FastAPI, facts: Known, proxies: Sequence[str] = PRIVATE ) -> None:

    engine.state.facts   = dict(facts)
    engine.state.proxies = tuple(proxies)

class Facts:

    @staticmethod
    def of ( request: Request ) -> Known:

        facts = request.shared("facts", {})

        return facts if isinstance(facts, Mapping) else {}

def by_client ( request: Request ) -> str:

    return request.ip()

class Throttle:

    def parse ( self, rate: str ) -> tuple[int, float]:

        return parse.rate(rate)

    def guard ( self, rate: str, key: Keyed = by_client, scope: str = "" ) -> Callable[[Request], Awaitable[None]]:

        limit, window = self.parse(rate)

        async def limited ( request: Request ) -> None:

            bucket = f"throttle:{scope or request.path()}:{key(request)}"
            hit    = await cache.hit(bucket, limit, window)

            request.assign(throttle={ "limit": limit, "remaining": hit.remaining, "reset": round(hit.reset, 1) })

            if not hit.allowed: raise Fault(Code.TOO_MANY_REQUESTS, reason="throttle", retry_after=round(hit.reset))

        limited.__name__ = f"throttle_{limit}_per_{int(window)}s"

        return limited
