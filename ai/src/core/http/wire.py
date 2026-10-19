from collections.abc import Sequence
from typing import Any

from fastapi import Request
from fnmatch import fnmatch

from core.net import net

JSON = "application/json"

class Wire:

    def __init__ ( self, request: Request ) -> None:

        self._request = request

    def request ( self ) -> Request:

        return self._request

    def header ( self, name: str, default: str = "" ) -> str:

        return self._request.headers.get(name, default)

    def headers ( self ) -> dict[str, str]:

        return dict(self._request.headers)

    def bearer ( self ) -> str | None:

        scheme, _, token = self.header("authorization").partition(" ")

        return token.strip() or None if scheme.lower() == "bearer" else None

    def ip ( self, trusted: Sequence[str] = () ) -> str:

        peer = self._request.client.host if self._request.client else ""

        return net.client_ip(self.header("x-forwarded-for"), peer, trusted)

    def method ( self ) -> str:

        return self._request.method

    def path ( self ) -> str:

        return self._request.url.path

    def url ( self ) -> str:

        return str(self._request.url)

    def route_name ( self ) -> str | None:

        route = self._request.scope.get("route")

        return getattr(route, "name", None) if route is not None else None

    def is_json ( self ) -> bool:

        return self.header("content-type").split(";")[0].strip().lower() == JSON

    def wants_json ( self ) -> bool:

        return JSON in self.header("accept", "*/*") or "*/*" in self.header("accept", "*/*")

    def accepts ( self, *kinds: str ) -> bool:

        accepted = self.header("accept", "*/*")

        return "*/*" in accepted or any(kind in accepted for kind in kinds)

    def is_secure ( self ) -> bool:

        return self._request.url.scheme == "https" or self.header("x-forwarded-proto") == "https"

    def is_method ( self, *methods: str ) -> bool:

        return self._request.method in { method.upper() for method in methods }

    def user ( self ) -> Any:

        return getattr(self._request.state, "user", None)

    def state ( self, key: str, default: object = None ) -> Any:

        return getattr(self._request.state, key, default)

    def user_agent ( self ) -> str:

        return self.header("user-agent")

    def ips ( self ) -> list[str]:

        hops = [hop.strip() for hop in self.header("x-forwarded-for").split(",") if hop.strip()]
        peer = self._request.client.host if self._request.client else ""

        return [*hops, *([peer] if peer else [])]

    def is_ ( self, *patterns: str ) -> bool:

        return any(fnmatch(self.path().strip("/"), pattern.strip("/")) for pattern in patterns)

    def route_is ( self, *patterns: str ) -> bool:

        name = self.route_name() or ""

        return any(fnmatch(name, pattern) for pattern in patterns)
