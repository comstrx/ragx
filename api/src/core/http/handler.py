from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from core.error import Fault, Faults
from core.exception import exception
from .response import Response

faults = Faults()

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
