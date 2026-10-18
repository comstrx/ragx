from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Self

from .code import Code

type Errors = Mapping[str, list[str]]

class Fault(Exception):

    __slots__ = ("code", "errors", "message", "reason", "status")

    def __init__ (
        self, code: Code, message: str | None = None,
        reason: str | None = None, errors: Errors | None = None, status: HTTPStatus | None = None,
    ) -> None:

        self.code    = code
        self.message = message or code.message()
        self.reason  = reason
        self.errors  = errors
        self.status  = status or code.status()

        super().__init__(self.message)

    def server ( self ) -> bool:
        return self.status >= HTTPStatus.INTERNAL_SERVER_ERROR

    def client ( self ) -> bool:
        return HTTPStatus.BAD_REQUEST <= self.status < HTTPStatus.INTERNAL_SERVER_ERROR

    def retryable ( self ) -> bool:
        return self.code in (Code.UNAVAILABLE, Code.TOO_MANY_REQUESTS)

    def because ( self, reason: str ) -> Self:
        return type(self)(self.code, self.message, reason, self.errors, self.status)

    def dump ( self ) -> dict[str, Any]:

        return {
            "code"    : self.code,
            "message" : self.message,
            "reason"  : self.reason,
            "errors"  : dict(self.errors) if self.errors else None,
            "status"  : int(self.status),
        }

    @classmethod
    def of ( cls, error: BaseException, code: Code = Code.INTERNAL, reason: str | None = None ) -> Fault:

        if isinstance(error, Fault): return error

        return cls(code, reason=reason or type(error).__name__)
