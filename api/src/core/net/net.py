from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from core.exceptions import Code, Fault
from core.json import json as codec
import httpx

type Query = Mapping[str, object]
type Headers = Mapping[str, str]

SUCCESS = range(200, 300)
JSON    = { "content-type": "application/json" }

@dataclass(frozen=True, slots=True)
class Reply:

    status  : int
    headers : dict[str, str]
    body    : bytes
    url     : str
    ms      : float = field(default=0.0)

    def ok ( self ) -> bool:
        return self.status in SUCCESS

    def text ( self ) -> str:
        return self.body.decode(errors="replace")

    def json ( self ) -> Any:

        return codec.loads(self.body) if self.body else None

class Net:

    def __init__ ( self ) -> None:

        self._client: httpx.AsyncClient | None = None

    def open ( self, wait: float = 10.0, headers: Headers | None = None, retries: int = 0 ) -> None:

        if self._client is not None: return

        transport    = httpx.AsyncHTTPTransport(retries=retries)
        self._client = httpx.AsyncClient(
            timeout=wait, headers=dict(headers or {}), transport=transport, follow_redirects=False,
        )

    async def close ( self ) -> None:

        if self._client is None: return

        client, self._client = self._client, None

        await client.aclose()

    async def request (
        self, method: str, url: str, params: Query | None = None, json: object = None,
        data: Mapping[str, object] | None = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        if self._client is None: self.open()
        if self._client is None: raise Fault(Code.INTERNAL, reason="net")

        content = codec.encode(json) if json is not None else None
        sent    = { **JSON, **(headers or {}) } if content is not None else dict(headers or {})

        try:

            answer = await self._client.request(
                method.upper(), url, params=self._query_(params), content=content, data=dict(data) if data else None,
                headers=sent, timeout=wait if wait is not None else httpx.USE_CLIENT_DEFAULT,
            )

        except httpx.TimeoutException as error: raise Fault(Code.UNAVAILABLE, reason="timeout") from error
        except httpx.HTTPError as error: raise Fault(Code.UNAVAILABLE, reason="network") from error

        elapsed = round(answer.elapsed.total_seconds() * 1000, 2)

        return Reply(answer.status_code, dict(answer.headers), answer.content, str(answer.url), elapsed)

    async def get (
        self, url: str, params: Query | None = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:
        return await self.request("GET", url, params=params, headers=headers, wait=wait)

    async def post (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:
        return await self.request("POST", url, json=json, headers=headers, wait=wait)

    async def put (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:
        return await self.request("PUT", url, json=json, headers=headers, wait=wait)

    async def patch (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:
        return await self.request("PATCH", url, json=json, headers=headers, wait=wait)

    async def delete ( self, url: str, headers: Headers | None = None, wait: float | None = None ) -> Reply:
        return await self.request("DELETE", url, headers=headers, wait=wait)

    def url ( self, base: str, *parts: str, **query: object ) -> str:

        path = "/".join(part.strip("/") for part in parts if part)
        full = urljoin(base.rstrip("/") + "/", path) if path else base
        tail = self._query_(query)

        return f"{full}?{urlencode(tail)}" if tail else full

    def origin ( self, url: str ) -> str:

        parts = urlsplit(url)

        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""

    def host ( self, url: str ) -> str:
        return urlsplit(url).hostname or ""

    def query ( self, url: str ) -> dict[str, str]:
        return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))

    def is_url ( self, text: str ) -> bool:

        parts = urlsplit(text)

        return parts.scheme in ("http", "https") and bool(parts.netloc)

    def is_ip ( self, text: str ) -> bool:

        try: ip_address(text)
        except ValueError: return False

        return True

    def _query_ ( self, params: Query | None ) -> dict[str, str]:
        return { key: str(value) for key, value in (params or {}).items() if value is not None }
