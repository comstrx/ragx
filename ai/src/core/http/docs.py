from collections.abc import Sequence
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference
from starlette.responses import HTMLResponse
from core.error import Code

class Documented(Protocol):

    @property
    def enabled ( self ) -> bool: ...

    @property
    def path ( self ) -> str: ...

    @property
    def openapi ( self ) -> str: ...

    @property
    def title ( self ) -> str: ...

    @property
    def description ( self ) -> str: ...

    @property
    def theme ( self ) -> str: ...

    @property
    def layout ( self ) -> str: ...

    @property
    def dark ( self ) -> bool: ...

    @property
    def sidebar ( self ) -> bool: ...

    @property
    def models ( self ) -> bool: ...

    @property
    def download ( self ) -> bool: ...

    @property
    def search ( self ) -> bool: ...

    @property
    def errors ( self ) -> bool: ...

    @property
    def servers ( self ) -> Sequence[str]: ...

    @property
    def tags ( self ) -> Sequence[str]: ...

    @property
    def hide ( self ) -> Sequence[str]: ...

FAILURES = (
    Code.BAD_REQUEST, Code.UNAUTHORIZED, Code.FORBIDDEN, Code.NOT_FOUND, Code.CONFLICT, Code.VALIDATION,
    Code.TOO_MANY_REQUESTS, Code.INTERNAL, Code.UNAVAILABLE,
)
STRINGS  = { "type": "array", "items": { "type": "string" } }
ENVELOPE = {
    "type"       : "object",
    "required"   : ["data", "message", "errors", "code", "reason", "meta"],
    "properties" : {
        "data"    : { "nullable": True },
        "message" : { "type": "string", "nullable": True },
        "errors"  : { "type": "object", "nullable": True, "additionalProperties": STRINGS },
        "code"    : { "type": "string", "enum": [code.value for code in Code] },
        "reason"  : { "type": "string", "nullable": True },
        "meta"    : { "type": "object", "properties": { "request_id": { "type": "string", "nullable": True } } },
    },
}
METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "trace")
FAILURE = { "application/json": { "schema": { "$ref": "#/components/schemas/Envelope" } } }

class Docs:

    def install ( self, app: FastAPI, settings: Documented ) -> None:

        if not settings.enabled: return

        app.state.docs = lambda: self.schema(app, settings)

        app.add_route(settings.path, self.page(app, settings), include_in_schema=False, name="docs")

    def page ( self, app: FastAPI, settings: Documented ) -> Any:

        async def scalar ( request: Request ) -> HTMLResponse:

            return get_scalar_api_reference(
                openapi_url=f"{request.scope.get('root_path', '')}{settings.openapi}",
                title=settings.title or app.title, theme=settings.theme, layout=settings.layout,
                dark_mode=settings.dark, show_sidebar=settings.sidebar, hide_models=not settings.models,
                document_download_type="both" if settings.download else "none", hide_search=not settings.search,
                telemetry=False,
            )

        return scalar

    def schema ( self, app: FastAPI, settings: Documented ) -> dict[str, Any]:

        if app.openapi_schema: return app.openapi_schema

        built = get_openapi(
            title=settings.title or app.title, version=app.version, description=settings.description or None,
            routes=app.routes, servers=[{ "url": server } for server in settings.servers] or None,
            tags=[{ "name": tag } for tag in settings.tags] or None,
        )

        if settings.hide: self.prune(built, set(settings.hide))
        if settings.errors: self.failures(built)

        app.openapi_schema = built

        return built

    def prune ( self, schema: dict[str, Any], hidden: set[str] ) -> None:

        paths: dict[str, dict[str, Any]] = schema.get("paths", {})

        for path in list(paths):

            for method in list(paths[path]):

                if set(paths[path][method].get("tags", ())) & hidden: del paths[path][method]

            if not paths[path]: del paths[path]

    def failures ( self, schema: dict[str, Any] ) -> None:

        schema.setdefault("components", {}).setdefault("schemas", {})["Envelope"] = ENVELOPE

        for operations in schema.get("paths", {}).values():

            for method, operation in operations.items():

                if method not in METHODS: continue

                responses: dict[str, Any] = operation.setdefault("responses", {})

                for code in FAILURES:

                    responses.setdefault(str(int(code.status())), { "description": code.message(), "content": FAILURE })
