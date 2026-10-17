from core.http import Route
from app.controllers import health, hello

routes = Route.group("", [
    Route.get("/health", health.index, name="health", tags=("health",)),
    Route.group("/v1", [
        Route.get("/hello", hello.index, name="hello", tags=("hello",)),
    ]),
])

__all__ = ["routes"]
