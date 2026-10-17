from collections.abc import Mapping
from http import HTTPStatus

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
