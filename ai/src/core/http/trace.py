from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from core.context import context
from core.exception import exception
from core.log import log
from .response import Response
import re, time

PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
LIMITS  = (("limit", "X-RateLimit-Limit"), ("remaining", "X-RateLimit-Remaining"), ("reset", "X-RateLimit-Reset"))

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
