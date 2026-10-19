from enum import StrEnum
from http import HTTPStatus
from typing import Self, assert_never

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
