from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.error import Fault
from .client import Client, Files
from .ip import Ip, Probe
from .reply import Reply, Sse, Transport
from .url import Url
import httpx, inspect

type Query = Mapping[str, object]
type Headers = Mapping[str, str]
type Answer = tuple[int, bytes, Mapping[str, str]]
SERVER_ERROR = 500

@dataclass(frozen=True, slots=True)
class Ask:

    method  : str
    url     : str
    headers : dict[str, str]
    body    : bytes

class Net(Url, Ip, Probe):

    def __init__ ( self ) -> None:

        self._default = Client()
        self._clients: dict[str, Client] = {}

    def client (
        self, name: str, base: str = "", headers: Headers | None = None, wait: float = 10.0, retries: int = 0,
    ) -> Client:

        found = self._clients.get(name)

        if found is None: found = self._clients[name] = Client(base, headers, wait, retries)

        return found

    def open ( self, wait: float = 10.0, headers: Headers | None = None, retries: int = 0 ) -> None:

        self._default.open(wait, headers, retries)

    async def close ( self ) -> None:

        await self._default.close()

        for client in self._clients.values(): await client.close()

    def asgi ( self, app: Any ) -> Transport:

        return Transport(httpx.ASGITransport(app=app))

    def mocked ( self, answer: Callable[[Ask], Answer | Awaitable[Answer]] ) -> Transport:

        async def handle ( request: httpx.Request ) -> httpx.Response:

            asked   = Ask(request.method, str(request.url), dict(request.headers), request.content)
            replied = answer(asked)
            status, body, headers = await replied if inspect.isawaitable(replied) else replied

            return httpx.Response(status, content=body, headers=headers)

        return Transport(httpx.MockTransport(handle))

    async def request (
        self, method: str, url: str, params: Query | None = None, json: object = None,
        data: Mapping[str, object] | None = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        return await self._default.request(method, url, params=params, json=json, data=data, headers=headers, wait=wait)

    async def get (
        self, url: str, params: Query | None = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        return await self._default.get(url, params, headers, wait)

    async def post (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        return await self._default.post(url, json, headers, wait)

    async def put (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        return await self._default.put(url, json, headers, wait)

    async def patch (
        self, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> Reply:

        return await self._default.patch(url, json, headers, wait)

    async def delete ( self, url: str, headers: Headers | None = None, wait: float | None = None ) -> Reply:

        return await self._default.delete(url, headers, wait)

    async def head ( self, url: str, headers: Headers | None = None, wait: float | None = None ) -> Reply:

        return await self._default.head(url, headers, wait)

    def stream (
        self, method: str, url: str, json: object = None, headers: Headers | None = None,
    ) -> AsyncIterator[bytes]:

        return self._default.stream(method, url, json, headers)

    def sse ( self, method: str, url: str, json: object = None, headers: Headers | None = None ) -> AsyncIterator[Sse]:

        return self._default.sse(method, url, json, headers)

    async def download ( self, url: str, target: Path, headers: Headers | None = None ) -> int:

        return await self._default.download(url, target, headers)

    async def upload ( self, url: str, files: Files, data: Mapping[str, object] | None = None ) -> Reply:

        return await self._default.upload(url, files, data)

    async def reachable ( self, url: str, wait: float = 3.0 ) -> bool:

        try: return (await self._default.head(url, wait=wait)).status < SERVER_ERROR
        except Fault: return False

    def bearer ( self, token: str ) -> dict[str, str]:

        return { "authorization": f"Bearer {token}" }

    def describe ( self ) -> dict[str, object]:

        return { "default": self._default.describe(), "clients": sorted(self._clients) }
