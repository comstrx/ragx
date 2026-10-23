from collections.abc import Sequence
from typing import Any

from engine.context import context
from engine.error import Fault, Faults
from engine.exception import exception
from engine.log import log
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from granian import Granian
from granian.constants import Interfaces
from granian.log import LogLevels
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from .response import Response
import re, time

faults = Faults()
PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LIMITS  = (("limit", "X-RateLimit-Limit"), ("remaining", "X-RateLimit-Remaining"), ("reset", "X-RateLimit-Reset"))

class Errors:

    def install ( self, app: FastAPI ) -> None:

        app.add_exception_handler(Fault, self.fault)
        app.add_exception_handler(RequestValidationError, self.validation)
        app.add_exception_handler(HTTPException, self.http)
        app.add_exception_handler(Exception, self.fault)

    async def fault ( self, request: Request, exc: Exception ) -> Response:

        return Response.fail(exception.handle(exc, method=request.method, path=request.url.path))

    async def validation ( self, _: Request, exc: Exception ) -> Response:

        details = exc.errors() if isinstance(exc, RequestValidationError) else []

        return Response.fail(faults.validation(self.errors(details)))

    async def http ( self, _: Request, exc: Exception ) -> Response:

        status = exc.status_code if isinstance(exc, HTTPException) else 500
        detail = exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else None

        return Response.fail(faults.status(status, detail))

    def errors ( self, details: Sequence[Any] ) -> dict[str, list[str]]:

        errors: dict[str, list[str]] = {}

        for detail in details:

            loc   = [str(part) for part in detail.get("loc", ())]
            field = ".".join(loc[1:]) or ".".join(loc) or "body"

            errors.setdefault(field, []).append(str(detail.get("msg", "invalid")))

        return errors

class Trace:

    header = "X-Request-Id"

    def __init__ ( self, app: ASGIApp ) -> None:

        self.app = app

    async def __call__ ( self, scope: Scope, receive: Receive, send: Send ) -> None:

        if scope["type"] != "http": return await self.app(scope, receive, send)

        incoming = Headers(scope=scope).get(self.header)
        token    = context.start(incoming if incoming and PATTERN.match(incoming) else None)
        started  = time.perf_counter()
        status   = 0

        async def stamped ( message: Message ) -> None:

            nonlocal status

            if message["type"] == "http.response.start":

                status  = int(message["status"])
                headers = MutableHeaders(scope=message)

                headers.append(self.header, context.request_id() or "")
                headers.append("X-Content-Type-Options", "nosniff")

                for name, header in LIMITS:

                    value = self.throttled(scope).get(name)

                    if value is not None: headers.append(header, str(value))

            await send(message)

        try: await self.app(scope, receive, stamped)
        except Exception as exc:

            if status: raise

            fault = exception.handle(exc, method=scope["method"], path=scope["path"])

            await Response.fail(fault)(scope, receive, stamped)

            raise

        finally:

            elapsed = round((time.perf_counter() - started) * 1000, 2)
            log.info("http.request", method=scope["method"], path=scope["path"], status=status, ms=elapsed)
            context.finish(token)

        return None

    def throttled ( self, scope: Scope ) -> dict[str, object]:

        state = scope.get("state")
        found = state.get("throttle") if isinstance(state, dict) else None

        return dict(found) if isinstance(found, dict) else {}

class Warm:

    async def hit ( self, app: ASGIApp, path: str, method: str = "GET" ) -> int:

        status = 0
        scope: Scope = {
            "type": "http", "asgi": { "version": "3.0" }, "http_version": "1.1", "method": method,
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
            "headers": [(b"host", b"warm")], "client": ("127.0.0.1", 0), "server": ("127.0.0.1", 0),
        }

        async def receive () -> Message:

            return { "type": "http.request", "body": b"", "more_body": False }

        async def send ( message: Message ) -> None:

            nonlocal status

            if message["type"] == "http.response.start": status = int(message["status"])

        await app(scope, receive, send)

        return status

    async def paths ( self, app: ASGIApp, paths: tuple[str, ...] ) -> dict[str, int]:

        return { path: await self.hit(app, path) for path in paths }

class Server:

    def run (
        self, target: str, host: str = "127.0.0.1", port: int = 8000,
        workers: int = 1, reload: bool = False, level: str = "info",
    ) -> None:

        Granian(
            target, address=host, port=port, interface=Interfaces.ASGI, workers=workers,
            reload=reload, factory=True, log_access=False, log_level=LogLevels(level),
        ).serve()
