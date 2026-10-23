from http import HTTPStatus
from typing import NoReturn

from .fault import Code, Errors, Fault

class Faults:

    def make (
        self, code: Code, reason: str | None = None, message: str | None = None, errors: Errors | None = None,
    ) -> Fault:

        return Fault(code, message, reason, errors)

    def bad_request ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.BAD_REQUEST, message, reason)

    def unauthorized ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.UNAUTHORIZED, message, reason)

    def forbidden ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.FORBIDDEN, message, reason)

    def not_found ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.NOT_FOUND, message, reason)

    def method_not_allowed ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.METHOD_NOT_ALLOWED, message, reason)

    def conflict ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.CONFLICT, message, reason)

    def validation ( self, errors: Errors, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.VALIDATION, message, reason, errors)

    def invalid ( self, field: str, message: str, reason: str | None = None ) -> Fault:

        return Fault(Code.VALIDATION, reason=reason or field, errors={ field: [message] })

    def too_many_requests ( self, reason: str | None = None, retry_after: float | None = None ) -> Fault:

        return Fault(Code.TOO_MANY_REQUESTS, reason=reason, retry_after=retry_after)

    def internal ( self, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.INTERNAL, message, reason)

    def unavailable ( self, reason: str | None = None, retry_after: float | None = None ) -> Fault:

        return Fault(Code.UNAVAILABLE, reason=reason, retry_after=retry_after)

    def timeout ( self, reason: str | None = None ) -> Fault:

        return Fault(Code.UNAVAILABLE, reason=reason or "timeout", unknown=True)

    def unsupported ( self, family: str, provider: str, capability: str ) -> Fault:

        return Fault(Code.INTERNAL, reason=f"{family}.{provider}.unsupported.{capability}")

    def status ( self, status: int, reason: str | None = None, message: str | None = None ) -> Fault:

        return Fault(Code.of(status), message, reason, status=HTTPStatus(status))

    def wrap ( self, error: BaseException, code: Code = Code.INTERNAL, reason: str | None = None ) -> Fault:

        return Fault.of(error, code, reason)

    def throw (
        self, code: Code, reason: str | None = None, message: str | None = None, errors: Errors | None = None,
    ) -> NoReturn:

        raise Fault(code, message, reason, errors)

    def throw_if (
        self, condition: object, code: Code, reason: str | None = None, message: str | None = None,
        errors: Errors | None = None,
    ) -> None:

        if condition: raise Fault(code, message, reason, errors)

    def throw_unless (
        self, condition: object, code: Code, reason: str | None = None, message: str | None = None,
        errors: Errors | None = None,
    ) -> None:

        if not condition: raise Fault(code, message, reason, errors)

    def abort ( self, status: int, reason: str | None = None, message: str | None = None ) -> NoReturn:

        raise self.status(status, reason, message)

    def abort_if ( self, condition: object, status: int, reason: str | None = None ) -> None:

        if condition: raise self.status(status, reason)

    def abort_unless ( self, condition: object, status: int, reason: str | None = None ) -> None:

        if not condition: raise self.status(status, reason)

    def ensure[T] ( self, value: T | None, code: Code = Code.NOT_FOUND, reason: str | None = None ) -> T:

        if value is None: raise Fault(code, reason=reason)

        return value

    def codes ( self ) -> tuple[Code, ...]:

        return tuple(Code)
