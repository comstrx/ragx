from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, override

from fastapi import Depends, FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import Response as Served
from starlette.staticfiles import StaticFiles
from .docs import Documented, Docs
from .facts import Facts, Known
from .handler import Errors
from .response import Response
from .route import Group
from .router import Router
from .throttle import Throttle
from .trace import Trace

type Lifespan = Callable[[App], AbstractAsyncContextManager[None]]
type Schema = Callable[[], dict[str, Any]]

throttle = Throttle()

class Static(StaticFiles):

    def __init__ ( self, folder: Path, cache: int ) -> None:

        super().__init__(directory=str(folder), check_dir=False)

        self._cache = cache

    @override
    def file_response ( self, *args: Any, **kwargs: Any ) -> Served:

        response = super().file_response(*args, **kwargs)

        if self._cache: response.headers["Cache-Control"] = f"public, max-age={self._cache}, immutable"

        return response

class App(FastAPI):

    @override
    def openapi ( self ) -> dict[str, Any]:

        decorate: Schema | None = getattr(self.state, "docs", None)

        return decorate() if decorate else super().openapi()

class Http:

    def __init__ ( self ) -> None:

        self._router = Router()

    def router ( self, app: FastAPI | None = None ) -> Router:

        found = getattr(app.state, "router", None) if app is not None else None

        return found if isinstance(found, Router) else self._router

    def url ( self, name: str, **params: object ) -> str:

        return self._router.url(name, **params)

    def has ( self, name: str ) -> bool:

        return self._router.has(name)

    def build (
        self, title: str, version: str, groups: Sequence[Group],
        debug: bool = False, docs: Documented | None = None, facts: Known | None = None,
        origins: Sequence[str] = (), lifespan: Lifespan | None = None,
    ) -> App:

        app = App(
            title=title, version=version, debug=debug, openapi_url=docs.openapi if docs and docs.enabled else None,
            docs_url=None, redoc_url=None, default_response_class=Response, lifespan=lifespan,
        )

        Facts.keep(app, facts or {})
        app.add_middleware(Trace)

        self._router     = Router()
        app.state.router = self._router

        if origins: self.share(app, origins)
        Errors().install(app)

        for group in groups: self.mount(app, group)

        if docs: Docs().install(app, docs)

        return app

    def share ( self, app: FastAPI, origins: Sequence[str] ) -> None:

        app.add_middleware(
            CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"],
            expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
            max_age=600,
        )

    def serve ( self, app: FastAPI, url: str, folder: Path, name: str = "static", cache: int = 0 ) -> None:

        folder.mkdir(parents=True, exist_ok=True)
        app.mount(url, Static(folder, cache), name=name)

    def mount ( self, app: FastAPI, group: Group ) -> None:

        self.router(app).register(group)

        for bound in group.walk():

            guards = [Depends(guard) for guard in bound.middleware]

            if bound.throttle: guards.append(Depends(throttle.guard(bound.throttle, scope=bound.name or bound.path)))

            app.add_api_route(
                bound.path, bound.handler, methods=list(bound.methods), name=bound.name, tags=list(bound.tags),
                dependencies=guards,
            )
