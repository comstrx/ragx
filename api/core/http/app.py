from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from .facts import Facts, Known
from .handler import Handler
from .response import Response
from .route import Group
from .trace import Trace

type Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class Http:

    def build (
        self, title: str, version: str, groups: Sequence[Group],
        debug: bool = False, openapi_url: str | None = "/openapi.json", facts: Known | None = None,
        origins: Sequence[str] = (), lifespan: Lifespan | None = None,
    ) -> FastAPI:

        app = FastAPI(
            title=title, version=version, debug=debug, openapi_url=openapi_url,
            docs_url=None, redoc_url=None, default_response_class=Response, lifespan=lifespan,
        )

        Facts.keep(app, facts or {})
        app.add_middleware(Trace)

        if origins: self.share(app, origins)
        Handler().install(app)

        for group in groups: self.mount(app, group)

        return app

    def share ( self, app: FastAPI, origins: Sequence[str] ) -> None:

        app.add_middleware(
            CORSMiddleware, allow_origins=list(origins), allow_methods=["*"], allow_headers=["*"],
            expose_headers=["X-Request-Id"], max_age=600,
        )

    def mount ( self, app: FastAPI, group: Group ) -> None:

        for path, tags, route in group.walk():
            app.add_api_route(path, route.handler, methods=[route.method], name=route.name, tags=list(tags))
