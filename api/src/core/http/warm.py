from starlette.types import ASGIApp, Message, Scope

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
