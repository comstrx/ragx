from core.http import Docs, Route

routes = Route.group("/docs", [
    Route.get("", Docs.scalar, name="docs", tags=("docs",)),
])

__all__ = ["routes"]
