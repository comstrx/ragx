from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, override

from .code import Code

type Errors = Mapping[str, list[str]]

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
