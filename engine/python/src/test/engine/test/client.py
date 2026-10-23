from collections.abc import Iterator, Mapping, Sequence
from contextlib import AsyncExitStack, contextmanager
from types import TracebackType
from typing import Any, Protocol, Self, override

from httpx import ASGITransport, AsyncClient, Request as Sent, Response as Received
from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect, WebSocketState
from engine.error import Code
from engine.http import App
from engine.json import json
from .expect import Expect, dig, mismatch
import asyncio

type Files = Mapping[str, tuple[str, bytes, str]]
type Fields = Mapping[str, object]
type Query = Mapping[str, str | int | float | bool | Sequence[str] | None]

class Reply(Protocol):

    @property
    def status_code ( self ) -> int: ...

    @property
    def headers ( self ) -> Mapping[str, str]: ...

    @property
    def content ( self ) -> bytes: ...

    @property
    def text ( self ) -> str: ...

    @property
    def cookies ( self ) -> Mapping[str, str]: ...

class Answer:

    __slots__ = ("_reply",)

    def __init__ ( self, reply: Reply ) -> None:

        self._reply = reply

    @property
    def code ( self ) -> int:

        return self._reply.status_code

    @property
    def headers ( self ) -> dict[str, str]:

        return dict(self._reply.headers)

    @property
    def content ( self ) -> bytes:

        return self._reply.content

    def text ( self ) -> str:

        return self._reply.text

    def json ( self ) -> Any:

        return json.loads(self._reply.content) if self._reply.content else None

    def data ( self, path: str = "" ) -> Any:

        body = self.json()
        data = body.get("data") if isinstance(body, Mapping) else None

        return dig(data, path) if path else data

    def cookie ( self, name: str ) -> str | None:

        return self._reply.cookies.get(name)

    def expect ( self, path: str = "" ) -> Expect:

        return Expect(dig(self.json(), path) if path else self.json(), path or "body")

    def status ( self, code: int ) -> Self:

        if self.code != code: mismatch(f"expected status {code}, got {self.code}: {self._reply.text[:300]}")

        return self

    def ok ( self ) -> Self:

        return self.status(200)

    def created ( self ) -> Self:

        return self.status(201)

    def fault ( self, code: Code, reason: str | None = None, field: str | None = None ) -> Self:

        self.status(int(code.status()))

        body   = self.json() if isinstance(self.json(), Mapping) else {}
        errors = body.get("errors") or {}

        if body.get("code") != code.value: mismatch(f"expected code {code.value}, got {body.get('code')!r}")
        if reason is not None and body.get("reason") != reason:
            mismatch(f"expected reason {reason!r}, got {body.get('reason')!r}")
        if field is not None and field not in errors: mismatch(f"expected an error on {field!r}, got {errors!r}")

        return self

    def header ( self, name: str, value: str | None = None ) -> Self:

        found = self._reply.headers.get(name)

        if found is None: mismatch(f"expected header {name!r}")
        if value is not None and found != value: mismatch(f"expected header {name}={value!r}, got {found!r}")

        return self

    def lacks ( self, name: str ) -> Self:

        if name in self._reply.headers: mismatch(f"expected no header {name!r}, got {self._reply.headers[name]!r}")

        return self

class Isolated(ASGITransport):

    @override
    async def handle_async_request ( self, request: Sent ) -> Received:

        return await asyncio.create_task(super().handle_async_request(request))

class Client:

    def __init__ (
        self, app: App, base: str = "http://test", peer: tuple[str, int] = ("127.0.0.1", 50000),
        lifespan: bool = False, headers: Mapping[str, str] | None = None,
    ) -> None:

        self._app      = app
        self._lifespan = lifespan
        self._stack    = AsyncExitStack()
        transport      = Isolated(app=app, raise_app_exceptions=False, client=peer)
        self._client   = AsyncClient(transport=transport, base_url=base, headers=dict(headers or {}))

    async def __aenter__ ( self ) -> Self:

        if self._lifespan: await self._stack.enter_async_context(self._app.lifespan())

        await self._stack.enter_async_context(self._client)

        return self

    async def __aexit__ (
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None,
    ) -> None:

        await self._stack.__aexit__(kind, error, trace)

    async def request (
        self, method: str, path: str, *, json: object = None, data: Fields | None = None, files: Files | None = None,
        params: Query | None = None, headers: Mapping[str, str] | None = None, content: bytes | None = None,
    ) -> Answer:

        reply = await self._client.request(
            method, path, json=json, data=dict(data) if data else None, files=dict(files) if files else None,
            params=dict(params) if params else None, headers=dict(headers or {}), content=content,
        )

        return Answer(reply)

    async def get ( self, path: str, **options: Any ) -> Answer:

        return await self.request("GET", path, **options)

    async def post ( self, path: str, **options: Any ) -> Answer:

        return await self.request("POST", path, **options)

    async def put ( self, path: str, **options: Any ) -> Answer:

        return await self.request("PUT", path, **options)

    async def patch ( self, path: str, **options: Any ) -> Answer:

        return await self.request("PATCH", path, **options)

    async def delete ( self, path: str, **options: Any ) -> Answer:

        return await self.request("DELETE", path, **options)

    async def options ( self, path: str, **options: Any ) -> Answer:

        return await self.request("OPTIONS", path, **options)

class Peer:

    __slots__ = ("_session",)

    def __init__ ( self, session: WebSocketTestSession ) -> None:

        self._session = session

    def send ( self, frame: Mapping[str, object] ) -> None:

        self._session.send_json(dict(frame))

    def text ( self, raw: str ) -> None:

        self._session.send_text(raw)

    def receive ( self ) -> dict[str, Any]:

        found: dict[str, Any] = self._session.receive_json(mode="binary")

        return found

    def frames ( self, count: int ) -> list[dict[str, Any]]:

        return [self.receive() for _ in range(count)]

    def closed ( self ) -> int:

        try: found = self.receive()
        except WebSocketDisconnect as gone: return gone.code

        return mismatch(f"expected the socket to close, got {found!r}")

class Sockets:

    __slots__ = ("_client",)

    def __init__ ( self, client: TestClient ) -> None:

        self._client = client

    def post ( self, path: str, json: object = None ) -> Answer:

        return Answer(self._client.post(path, json=json))

    def get ( self, path: str ) -> Answer:

        return Answer(self._client.get(path))

    @contextmanager
    def connect ( self, path: str ) -> Iterator[Peer]:

        with self._client.websocket_connect(path) as session: yield Peer(session)

    def refused ( self, path: str ) -> int:

        try:
            with self._client.websocket_connect(path) as session: session.receive_json(mode="binary")
        except WebSocketDisconnect as gone: return gone.code

        return mismatch(f"expected {path} to be refused")

class Stub:

    client_state = WebSocketState.CONNECTED

    def __init__ ( self ) -> None:

        self.sent: list[bytes] = []
        self.closed: tuple[int, str | None] | None = None

    async def send_bytes ( self, data: bytes ) -> None:

        self.sent.append(data)

    async def receive ( self ) -> dict[str, object]:

        return { "type": "websocket.disconnect", "code": 1000 }

    async def close ( self, code: int = 1000, reason: str | None = None ) -> None:

        self.closed = (code, reason)

    def frames ( self ) -> list[Any]:

        return [json.loads(frame) for frame in self.sent]
