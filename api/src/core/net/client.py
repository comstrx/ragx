from collections.abc import AsyncGenerator, Callable, Mapping
from pathlib import Path
from typing import Any, override

from core.error import Code, Fault
from core.fs import fs
from core.json import json as codec
from .fluent import Breaker, Fluent, Hooks
from .reply import REJECTED, RETRYABLE, SUCCESS, Frames, Reply, Sse, Transport, pause_of, repeatable_of
import asyncio, contextlib, httpx, time

type Query = Mapping[str, object]
type Headers = Mapping[str, str]
type Files = Mapping[str, tuple[str, bytes, str]]
type Guard = Callable[[Reply], None]

JSON   = { "content-type": "application/json" }
SERVER = 500

class Client(Fluent):

    def __init__ (
        self, base: str = "", headers: Headers | None = None, wait: float = 10.0, retries: int = 0,
        backoff: float = 0.5, transport: Transport | None = None, breaker: Breaker | None = None,
    ) -> None:

        self._base      = base.rstrip("/")
        self._headers   = dict(headers or {})
        self._wait      = wait
        self._retries   = retries
        self._backoff   = backoff
        self._transport = transport.inner if transport is not None else None
        self._breaker   = breaker
        self._redirects = 0
        self._direct    = False
        self._client: httpx.AsyncClient | None = None
        self.hooks      = Hooks.empty()

    def open ( self, wait: float | None = None, headers: Headers | None = None, retries: int | None = None ) -> Client:

        if self._client is not None: return self

        if wait is not None: self._wait = wait
        if headers: self._headers.update(headers)
        if retries is not None: self._retries = retries

        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=self._wait, headers=self._headers, follow_redirects=self._redirects > 0,
            max_redirects=self._redirects, transport=self._transport or httpx.AsyncHTTPTransport(retries=0),
            trust_env=not self._direct,
        )

        return self

    def outbound ( self, redirects: int, direct: bool = True ) -> Client:

        self._redirects = redirects
        self._direct    = direct

        return self

    async def close ( self ) -> None:

        if self._client is None: return

        client, self._client = self._client, None

        await client.aclose()

    def _handle_ ( self ) -> httpx.AsyncClient:

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

        attempts   = self._retries + 1
        prepared   = self.prepare(params, json, data, headers)
        timeout    = wait if wait is not None else httpx.USE_CLIENT_DEFAULT
        repeatable = repeatable_of(method, headers)

        for attempt in range(1, attempts + 1):

            last    = attempt == attempts
            started = time.perf_counter()

            try:

                answer = await self._handle_().request(
                    method.upper(), url, files=dict(files) if files else None, timeout=timeout, **prepared,
                )

            except (httpx.ConnectError, httpx.ConnectTimeout) as error:

                if last: raise Fault(Code.UNAVAILABLE, reason="network") from error

                await asyncio.sleep(self._backoff * attempt)

                continue

            except httpx.TimeoutException as error:

                if last or not repeatable: raise Fault(Code.UNAVAILABLE, reason="timeout", unknown=True) from error

                await asyncio.sleep(self._backoff * attempt)

                continue

            except httpx.HTTPError as error:

                if last or not repeatable: raise Fault(Code.UNAVAILABLE, reason="network", unknown=True) from error

                await asyncio.sleep(self._backoff * attempt)

                continue

            status = answer.status_code

            if not last and (status in REJECTED or (status in RETRYABLE and repeatable)):

                await asyncio.sleep(pause_of(answer.headers.get("retry-after"), self._backoff * attempt))

                continue

            elapsed = round((time.perf_counter() - started) * 1000, 2)

            return Reply(status, dict(answer.headers), answer.content, str(answer.url), elapsed)

        raise Fault(Code.UNAVAILABLE, reason="network")

    @override
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
        guard: Guard | None = None,
    ) -> AsyncGenerator[bytes]:

        prepared = self.prepare(None, json, None, headers)
        timeout  = wait if wait is not None else httpx.USE_CLIENT_DEFAULT
        started  = time.perf_counter()

        try:

            async with self._handle_().stream(
                method.upper(), url, content=prepared["content"], headers=prepared["headers"], timeout=timeout,
            ) as answer:

                if answer.status_code not in SUCCESS:

                    await answer.aread()

                    elapsed = round((time.perf_counter() - started) * 1000, 2)

                    if guard is not None:
                        guard(Reply(answer.status_code, dict(answer.headers), answer.content, str(answer.url), elapsed))

                    raise Fault(Code.of(answer.status_code), reason="upstream")

                async for chunk in answer.aiter_bytes(): yield chunk

        except httpx.TimeoutException as error: raise Fault(Code.UNAVAILABLE, reason="timeout", unknown=True) from error
        except httpx.HTTPError as error: raise Fault(Code.UNAVAILABLE, reason="network", unknown=True) from error

    async def lines (
        self, method: str, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
        guard: Guard | None = None,
    ) -> AsyncGenerator[str]:

        buffer = b""

        async with contextlib.aclosing(self.stream(method, url, json, headers, wait, guard)) as chunks:

            async for chunk in chunks:

                buffer += chunk

                while b"\n" in buffer:

                    line, buffer = buffer.split(b"\n", 1)

                    yield line.decode(errors="replace").rstrip("\r")

        if buffer: yield buffer.decode(errors="replace")

    async def sse (
        self, method: str, url: str, json: object = None, headers: Headers | None = None, wait: float | None = None,
        guard: Guard | None = None,
    ) -> AsyncGenerator[Sse]:

        frames = Frames()
        asked  = { "accept": "text/event-stream", **(headers or {}) }

        async with contextlib.aclosing(self.lines(method, url, json, asked, wait, guard)) as rows:

            async for line in rows:

                if (packet := frames.feed(line)) is not None: yield packet

        if (packet := frames.flush()) is not None: yield packet

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
