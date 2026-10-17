from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from .docs import Documented, Docs
from .facts import Facts, Known
from .handler import Errors
from .response import Response
from .route import Group
from .throttle import Throttle
from .trace import Trace

type Lifespan = Callable[[App], AbstractAsyncContextManager[None]]
type Schema = Callable[[], dict[str, Any]]

throttle = Throttle()

class App(FastAPI):

    def openapi ( self ) -> dict[str, Any]:

        decorate: Schema | None = getattr(self.state, "docs", None)

        return decorate() if decorate else super().openapi()

class Http:

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

    def serve ( self, app: FastAPI, url: str, folder: Path, name: str = "static" ) -> None:

        folder.mkdir(parents=True, exist_ok=True)
        app.mount(url, StaticFiles(directory=str(folder)), name=name)

    def mount ( self, app: FastAPI, group: Group ) -> None:

        for bound in group.walk():

            guards = [Depends(guard) for guard in bound.middleware]

            if bound.throttle: guards.append(Depends(throttle.guard(bound.throttle, scope=bound.name or bound.path)))

            app.add_api_route(
                bound.path, bound.handler, methods=list(bound.methods), name=bound.name, tags=list(bound.tags),
                dependencies=guards,
            )
