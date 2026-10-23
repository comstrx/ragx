from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus
from typing import Any, Self, assert_never, override

type Errors = Mapping[str, list[str]]

class Code(StrEnum):

    OK                 = "ok"
    CREATED            = "created"
    ACCEPTED           = "accepted"
    BAD_REQUEST        = "bad_request"
    UNAUTHORIZED       = "unauthorized"
    FORBIDDEN          = "forbidden"
    NOT_FOUND          = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CONFLICT           = "conflict"
    VALIDATION         = "validation"
    TOO_MANY_REQUESTS  = "too_many_requests"
    INTERNAL           = "internal"
    UNAVAILABLE        = "unavailable"

    def status ( self ) -> HTTPStatus:

        match self:
            case Code.OK:                 return HTTPStatus.OK
            case Code.CREATED:            return HTTPStatus.CREATED
            case Code.ACCEPTED:           return HTTPStatus.ACCEPTED
            case Code.BAD_REQUEST:        return HTTPStatus.BAD_REQUEST
            case Code.UNAUTHORIZED:       return HTTPStatus.UNAUTHORIZED
            case Code.FORBIDDEN:          return HTTPStatus.FORBIDDEN
            case Code.NOT_FOUND:          return HTTPStatus.NOT_FOUND
            case Code.METHOD_NOT_ALLOWED: return HTTPStatus.METHOD_NOT_ALLOWED
            case Code.CONFLICT:           return HTTPStatus.CONFLICT
            case Code.VALIDATION:         return HTTPStatus.UNPROCESSABLE_CONTENT
            case Code.TOO_MANY_REQUESTS:  return HTTPStatus.TOO_MANY_REQUESTS
            case Code.INTERNAL:           return HTTPStatus.INTERNAL_SERVER_ERROR
            case Code.UNAVAILABLE:        return HTTPStatus.SERVICE_UNAVAILABLE
            case _:                       assert_never(self)

    def message ( self ) -> str:

        match self:
            case Code.OK:                 return "Done"
            case Code.CREATED:            return "Created"
            case Code.ACCEPTED:           return "Accepted"
            case Code.BAD_REQUEST:        return "The request is malformed"
            case Code.UNAUTHORIZED:       return "Authentication is required"
            case Code.FORBIDDEN:          return "This action is not allowed"
            case Code.NOT_FOUND:          return "The resource was not found"
            case Code.METHOD_NOT_ALLOWED: return "The method is not allowed"
            case Code.CONFLICT:           return "The request conflicts with the current state"
            case Code.VALIDATION:         return "The given data is invalid"
            case Code.TOO_MANY_REQUESTS:  return "Too many requests"
            case Code.INTERNAL:           return "Something went wrong"
            case Code.UNAVAILABLE:        return "The service is unavailable"
            case _:                       assert_never(self)

    def success ( self ) -> bool:

        return self.status() < HTTPStatus.BAD_REQUEST

    def client ( self ) -> bool:

        return HTTPStatus.BAD_REQUEST <= self.status() < HTTPStatus.INTERNAL_SERVER_ERROR

    def server ( self ) -> bool:

        return self.status() >= HTTPStatus.INTERNAL_SERVER_ERROR

    def transient ( self ) -> bool:

        return self in (Code.UNAVAILABLE, Code.TOO_MANY_REQUESTS)

    @classmethod
    def of ( cls, status: int ) -> Self:

        for code in cls:

            if code.status() == status: return code

        if status >= HTTPStatus.INTERNAL_SERVER_ERROR: return cls(cls.INTERNAL)
        if status >= HTTPStatus.BAD_REQUEST: return cls(cls.BAD_REQUEST)

        return cls(cls.OK)

    @classmethod
    def parse ( cls, text: str, default: Code | None = None ) -> Code | None:

        wanted = text.strip().lower().replace("-", "_").replace(" ", "_")

        return next((code for code in cls if code.value == wanted), default)

    @classmethod
    def failures ( cls ) -> tuple[Code, ...]:

        return tuple(code for code in cls if not code.success())

class Fault(Exception):

    __slots__ = ("code", "errors", "message", "reason", "retry_after", "status", "unknown")

    def __init__ (
        self, code: Code, message: str | None = None, reason: str | None = None, errors: Errors | None = None,
        status: HTTPStatus | None = None, *, retry_after: float | None = None, unknown: bool = False,
    ) -> None:

        self.code        = code
        self.message     = message or code.message()
        self.reason      = reason
        self.errors      = { field: list(messages) for field, messages in errors.items() } if errors else None
        self.status      = status or code.status()
        self.retry_after = retry_after
        self.unknown     = unknown

        super().__init__(self.message)

    def server ( self ) -> bool:

        return self.status >= HTTPStatus.INTERNAL_SERVER_ERROR

    def client ( self ) -> bool:

        return HTTPStatus.BAD_REQUEST <= self.status < HTTPStatus.INTERNAL_SERVER_ERROR

    def retryable ( self ) -> bool:

        return self.code.transient()

    def safe ( self, idempotent: bool = False ) -> bool:

        return self.retryable() and (idempotent or not self.unknown)

    def because ( self, reason: str ) -> Fault:

        return self.copy(reason=reason)

    def saying ( self, message: str ) -> Fault:

        return self.copy(message=message)

    def with_errors ( self, errors: Errors ) -> Fault:

        return self.copy(errors=errors)

    def after ( self, seconds: float ) -> Fault:

        return self.copy(retry_after=max(seconds, 0.0))

    def uncertain ( self ) -> Fault:

        return self.copy(unknown=True)

    def copy (
        self, *, message: str | None = None, reason: str | None = None, errors: Errors | None = None,
        retry_after: float | None = None, unknown: bool | None = None,
    ) -> Fault:

        fault = Fault(
            self.code, message or self.message, reason or self.reason, self.errors if errors is None else errors,
            self.status, retry_after=self.retry_after if retry_after is None else retry_after,
            unknown=self.unknown if unknown is None else unknown,
        )

        fault.__cause__ = self.__cause__ or self

        return fault

    def first ( self, field: str | None = None ) -> str | None:

        if not self.errors: return None
        if field is not None: return next(iter(self.errors.get(field, ())), None)

        return next((messages[0] for messages in self.errors.values() if messages), None)

    def dump ( self ) -> dict[str, Any]:

        dumped: dict[str, Any] = {
            "code"    : self.code.value,
            "message" : self.message,
            "reason"  : self.reason,
            "errors"  : dict(self.errors) if self.errors else None,
            "status"  : int(self.status),
        }

        if self.retry_after is not None: dumped["retry_after"] = self.retry_after
        if self.unknown: dumped["unknown"] = True

        return dumped

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Fault:

        code   = Code.parse(str(data.get("code", ""))) or Code.of(int(data.get("status") or HTTPStatus.BAD_REQUEST))
        errors = data.get("errors")
        status = data.get("status")
        retry  = data.get("retry_after")

        return Fault(
            code, data.get("message") or None, data.get("reason") or None, errors if isinstance(errors, dict) else None,
            HTTPStatus(int(status)) if status else None,
            retry_after=float(retry) if retry is not None else None, unknown=bool(data.get("unknown")),
        )

    @classmethod
    def of ( cls, error: BaseException, code: Code = Code.INTERNAL, reason: str | None = None ) -> Fault:

        if isinstance(error, Fault): return error

        fault = Fault(code, reason=reason or type(error).__name__)

        fault.__cause__ = error

        return fault

    @override
    def __reduce__ ( self ) -> tuple[Any, tuple[dict[str, Any]]]:

        return Fault.load, (self.dump(),)

    @override
    def __repr__ ( self ) -> str:

        reason = f", reason={self.reason!r}" if self.reason else ""

        return f"Fault({self.code.value}{reason})"
