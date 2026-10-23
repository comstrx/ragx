from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, TypedDict, Unpack, override

from engine.error import Code, Fault
from fastapi import Depends, FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response as Served
from starlette.routing import BaseRoute
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send
from .bind import Binder
from .docs import Docs, Documented
from .edge import Errors, Trace
from .response import Response
from .route import Group, Route
from .router import Known, Router, Throttle, keep
from .wire import PRIVATE

type Lifespan = Callable[[App], AbstractAsyncContextManager[None]]
type Socket = Callable[..., Awaitable[None]]
EXPOSED  = ["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"]

class Building(TypedDict, total=False):

    debug    : bool
    docs     : Documented | None
    facts    : Known | None
    origins  : Sequence[str]
    lifespan : Lifespan | None
    proxies  : Sequence[str]

throttle = Throttle()
binder   = Binder()

class Static(StaticFiles):

    def __init__ ( self, folder: Path, cache: int ) -> None:

        super().__init__(directory=str(folder), check_dir=False)

        self._cache = cache

    @override
    def file_response ( self, *args: Any, **kwargs: Any ) -> Served:

        response = super().file_response(*args, **kwargs)

        if self._cache: response.headers["Cache-Control"] = f"public, max-age={self._cache}, immutable"

        return response

class Engine(FastAPI):

    @override
    def openapi ( self ) -> dict[str, Any]:

        decorate: Callable[[], dict[str, Any]] | None = getattr(self.state, "docs", None)

        return decorate() if decorate else super().openapi()

class App:

    def __init__ ( self, title: str, version: str, **options: Unpack[Building] ) -> None:

        docs    = options.get("docs")
        origins = options.get("origins", ())

        self._title    = title
        self._version  = version
        self._lifespan = options.get("lifespan")
        self._router   = Router()
        self._engine   = Engine(
            title=title, version=version, debug=options.get("debug", False), docs_url=None, redoc_url=None,
            openapi_url=docs.openapi if docs and docs.enabled else None, default_response_class=Response,
            lifespan=self._span_ if self._lifespan else None,
        )

        keep(self._engine, options.get("facts") or {}, options.get("proxies", PRIVATE))

        self._engine.add_middleware(Trace)

        if origins: self.share(origins)

        Errors().install(self._engine)

    async def __call__ ( self, scope: Scope, receive: Receive, send: Send ) -> None:

        await self._engine(scope, receive, send)

    def _span_ ( self, _: FastAPI ) -> AbstractAsyncContextManager[None]:

        if self._lifespan is None: raise Fault(Code.INTERNAL, reason="http.lifespan")

        return self._lifespan(self)

    def title ( self ) -> str:

        return self._title

    def version ( self ) -> str:

        return self._version

    def router ( self ) -> Router:

        return self._router

    def share ( self, origins: Sequence[str] ) -> None:

        self._engine.add_middleware(
            CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"],
            expose_headers=EXPOSED, max_age=600,
        )

    def mount ( self, group: Group ) -> int:

        added = self._router.register(group)

        for bound in group.walk():

            guards = [Depends(binder.bind(guard, bound.methods)) for guard in bound.middleware]

            if bound.throttle:
                guards.append(Depends(binder.bind(throttle.guard(bound.throttle, scope=bound.name or bound.path))))

            self._engine.add_api_route(
                bound.path, binder.bind(bound.handler, bound.methods), methods=list(bound.methods), name=bound.name,
                tags=list(bound.tags), dependencies=guards, include_in_schema=not bound.hidden,
            )

        return added

    def route ( self, *routes: Route | Group ) -> int:

        return self.mount(Group("", tuple(routes)))

    def document ( self, docs: Documented ) -> None:

        Docs().install(self._engine, docs)

    def socket ( self, path: str, endpoint: Socket, name: str | None = None ) -> None:

        self._engine.add_api_websocket_route(path, endpoint, name=name)

    def serve ( self, url: str, folder: Path, name: str = "static", cache: int = 0 ) -> None:

        folder.mkdir(parents=True, exist_ok=True)

        self._engine.mount(url, Static(folder, cache), name=name)

    def openapi ( self ) -> dict[str, Any]:

        return self._engine.openapi()

    def lifespan ( self ) -> AbstractAsyncContextManager[object]:

        return self._engine.router.lifespan_context(self._engine)

    def names ( self ) -> list[str]:

        return [name for route in self._engine.routes if (name := self._name_of_(route))]

    def _name_of_ ( self, route: BaseRoute ) -> str:

        return str(getattr(route, "name", "") or "")

    def describe ( self ) -> dict[str, Any]:

        return { "title": self._title, "version": self._version, "routes": len(self._router.routes()) }

class Http:

    def __init__ ( self ) -> None:

        self._router = Router()

    def url ( self, name: str, **params: object ) -> str:

        return self._router.url(name, **params)

    def has ( self, name: str ) -> bool:

        return self._router.has(name)

    def build ( self, title: str, version: str, groups: Sequence[Group], **options: Unpack[Building] ) -> App:

        app  = App(title, version, **options)
        docs = options.get("docs")

        self._router = app.router()

        for group in groups: app.mount(group)

        if docs: app.document(docs)

        return app
