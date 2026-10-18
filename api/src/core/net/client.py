from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

from core.error import Code, Fault
from core.fs import fs
from core.json import json as codec
from .breaker import Breaker, Hooks
from .fluent import Fluent
from .reply import SUCCESS, Reply, Sse
import asyncio, httpx

type Query = Mapping[str, object]
type Headers = Mapping[str, str]
type Files = Mapping[str, tuple[str, bytes, str]]

JSON      = { "content-type": "application/json" }
SERVER    = 500
RETRYABLE = frozenset({408, 425, 429, 500, 502, 503, 504})
DATA      = "data:"
EVENT     = "event:"
ID        = "id:"
RETRY     = "retry:"

class Client(Fluent):

    def __init__ (
        self, base: str = "", headers: Headers | None = None, wait: float = 10.0, retries: int = 0,
        backoff: float = 0.5, transport: httpx.AsyncBaseTransport | None = None, breaker: Breaker | None = None,
    ) -> None:

        self._base      = base.rstrip("/")
        self._headers   = dict(headers or {})
        self._wait      = wait
        self._retries   = retries
        self._backoff   = backoff
        self._transport = transport
        self._breaker   = breaker
        self._client: httpx.AsyncClient | None = None
        self.hooks      = Hooks.empty()

    def open ( self, wait: float | None = None, headers: Headers | None = None, retries: int | None = None ) -> Client:

        if self._client is not None: return self

        if wait is not None: self._wait = wait
        if headers: self._headers.update(headers)
        if retries is not None: self._retries = retries

        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=self._wait, headers=self._headers, follow_redirects=False,
            transport=self._transport or httpx.AsyncHTTPTransport(retries=0),
        )

        return self

    async def close ( self ) -> None:

        if self._client is None: return

        client, self._client = self._client, None

        await client.aclose()

    def handle ( self ) -> httpx.AsyncClient:

        if self._client is None: self.open()
        if self._client is None: raise Fault(Code.INTERNAL, reason="net")

        return self._client

    def prepare (
        self, params: Query | None, json: object, data: Mapping[str, object] | None, headers: Headers | None,
    ) -> dict[str, Any]:

        content = codec.encode(json) if json is not None else None
        sent    = { **JSON, **(headers or {}) } if content is not None else dict(headers or {})
        query   = { key: str(value) for key, value in (params or {}).items() if value is not None }

        return { "params": query or None, "content": content, "data": dict(data) if data else None, "headers": sent }

    async def request (
        self, method: str, url: str, *, params: Query | None = None, json: object = None,
        data: Mapping[str, object] | None = None, headers: Headers | None = None, wait: float | None = None,
        files: Files | None = None,
    ) -> Reply:

        if self._breaker is not None: self._breaker.guard()

        await self.hooks.fire(self.hooks.before, method.upper(), url)

        try: reply = await self.attempt(method, url, params, json, data, headers, wait, files)
        except Fault as fault:

            if self._breaker is not None: self._breaker.fail()

            await self.hooks.fire(self.hooks.failed, method.upper(), url, fault)

            raise

        if self._breaker is not None and reply.status >= SERVER: self._breaker.fail()
        elif self._breaker is not None: self._breaker.succeed()

        await self.hooks.fire(self.hooks.after, reply)

        return reply

    async def attempt (
        self, method: str, url: str, params: Query | None, json: object, data: Mapping[str, object] | None,
        headers: Headers | None, wait: float | None, files: Files | None,
    ) -> Reply:

        attempts = self._retries + 1
        prepared = self.prepare(params, json, data, headers)
        timeout  = wait if wait is not None else httpx.USE_CLIENT_DEFAULT

        for attempt in range(1, attempts + 1):

            try:

                answer = await self.handle().request(
                    method.upper(), url, files=dict(files) if files else None, timeout=timeout, **prepared,
                )

            except httpx.TimeoutException as error:

                if attempt == attempts: raise Fault(Code.UNAVAILABLE, reason="timeout") from error

                await asyncio.sleep(self._backoff * attempt)

                continue

            except httpx.HTTPError as error:

                if attempt == attempts: raise Fault(Code.UNAVAILABLE, reason="network") from error

                await asyncio.sleep(self._backoff * attempt)

                continue

            if answer.status_code in RETRYABLE and attempt < attempts:

                await asyncio.sleep(self._backoff * attempt)

                continue

            elapsed = round(answer.elapsed.total_seconds() * 1000, 2)

            return Reply(answer.status_code, dict(answer.headers), answer.content, str(answer.url), elapsed)

        raise Fault(Code.UNAVAILABLE, reason="network")

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

    async def head ( self, url: str, headers: Headers | None = None, wait: float | None = None ) -> Reply:
        return await self.request("HEAD", url, headers=headers, wait=wait)

    async def stream (
        self, method: str, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> AsyncIterator[bytes]:

        prepared = self.prepare(None, json, None, headers)
        timeout  = wait if wait is not None else httpx.USE_CLIENT_DEFAULT

        try:

            async with self.handle().stream(
                method.upper(), url, content=prepared["content"], headers=prepared["headers"], timeout=timeout,
            ) as answer:

                if answer.status_code not in SUCCESS:

                    await answer.aread()

                    raise Fault(Code.of(answer.status_code), reason="upstream")

                async for chunk in answer.aiter_bytes(): yield chunk

        except httpx.TimeoutException as error: raise Fault(Code.UNAVAILABLE, reason="timeout") from error
        except httpx.HTTPError as error: raise Fault(Code.UNAVAILABLE, reason="network") from error

    async def lines (
        self, method: str, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> AsyncIterator[str]:

        buffer = b""

        async for chunk in self.stream(method, url, json, headers, wait):

            buffer += chunk

            while b"\n" in buffer:

                line, buffer = buffer.split(b"\n", 1)

                yield line.decode(errors="replace").rstrip("\r")

        if buffer: yield buffer.decode(errors="replace")

    async def sse (
        self, method: str, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
    ) -> AsyncIterator[Sse]:

        event: dict[str, Any] = {}
        data: list[str] = []

        async for line in self.lines(method, url, json, { "accept": "text/event-stream", **(headers or {}) }, wait):

            if line == "":

                if data: yield self.packet(event, data)

                event, data = {}, []

                continue

            if line.startswith(":"): continue
            if line.startswith(DATA): data.append(line[len(DATA):].lstrip())
            elif line.startswith(EVENT): event["event"] = line[len(EVENT):].strip()
            elif line.startswith(ID): event["id"] = line[len(ID):].strip()
            elif line.startswith(RETRY) and line[len(RETRY):].strip().isdigit(): event["retry"] = int(line[len(RETRY):])

        if data: yield self.packet(event, data)

    def packet ( self, event: dict[str, Any], data: list[str] ) -> Sse:
        return Sse("\n".join(data), str(event.get("event", "message")), event.get("id"), event.get("retry"))

    async def download ( self, url: str, target: Path, headers: Headers | None = None ) -> int:
        return await fs.file.write_stream(target, self.stream("GET", url, headers=headers))

    async def upload (
        self, url: str, files: Files, data: Mapping[str, object] | None = None, headers: Headers | None = None,
    ) -> Reply:
        return await self.request("POST", url, data=data, headers=headers, files=files)

    def describe ( self ) -> dict[str, object]:

        return {
            "base": self._base, "wait": self._wait, "retries": self._retries, "open": self._client is not None,
            "breaker": self._breaker.describe() if self._breaker else None,
        }
