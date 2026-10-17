from http import HTTPStatus

from .code import Code
from .fault import Errors, Fault


class Faults:

    def bad_request ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.BAD_REQUEST, reason=reason)

    def unauthorized ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.UNAUTHORIZED, reason=reason)

    def forbidden ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.FORBIDDEN, reason=reason)

    def not_found ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.NOT_FOUND, reason=reason)

    def method_not_allowed ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.METHOD_NOT_ALLOWED, reason=reason)

    def conflict ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.CONFLICT, reason=reason)

    def validation ( self, errors: Errors, reason: str | None = None ) -> Fault:
        return Fault(Code.VALIDATION, reason=reason, errors=errors)

    def too_many_requests ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.TOO_MANY_REQUESTS, reason=reason)

    def internal ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.INTERNAL, reason=reason)

    def unavailable ( self, reason: str | None = None ) -> Fault:
        return Fault(Code.UNAVAILABLE, reason=reason)

    def status ( self, status: int, reason: str | None = None ) -> Fault:
        return Fault(Code.of(status), reason=reason, status=HTTPStatus(status))
