from collections.abc import Callable, Mapping
from http import HTTPStatus
from typing import ClassVar, NoReturn

from core.log import log
from .code import Code
from .fault import Errors, Fault
from .faults import Faults

type Mapper = Callable[[BaseException], Fault]
type Facts = Mapping[str, object]

SERVER_ERROR = HTTPStatus.INTERNAL_SERVER_ERROR

class Handler:

    maps   : ClassVar[Mapping[type[BaseException], Code | Mapper]] = {}
    silent : ClassVar[tuple[type[BaseException], ...]] = ()
    faults = Faults()

    def fault_of ( self, error: BaseException ) -> Fault:

        if isinstance(error, Fault): return error

        for kind, target in self.maps.items():

            if isinstance(error, kind): return Fault(target) if isinstance(target, Code) else target(error)

        return self.faults.internal()

    def handle ( self, error: BaseException, **facts: object ) -> Fault:

        fault = self.fault_of(error)

        self.report(error, fault, facts)

        return fault

    def report ( self, error: BaseException, fault: Fault, facts: Facts ) -> None:

        if isinstance(error, self.silent): return

        if fault.status >= SERVER_ERROR:
            log.exception(
                "exception.unhandled", kind=type(error).__name__, code=fault.code, reason=fault.reason, **facts,
            )
            return

        log.debug("exception.handled", code=fault.code, reason=fault.reason, **facts)

class Exceptions:

    def __init__ ( self ) -> None:

        self._handler = Handler()

    def use ( self, handler: Handler ) -> None:

        self._handler = handler

    def handler ( self ) -> Handler:
        return self._handler

    def fault_of ( self, error: BaseException ) -> Fault:
        return self._handler.fault_of(error)

    def handle ( self, error: BaseException, **facts: object ) -> Fault:
        return self._handler.handle(error, **facts)

    def throw (
        self, code: Code, message: str | None = None, reason: str | None = None, errors: Errors | None = None,
    ) -> NoReturn:
        raise Fault(code, message, reason, errors)

    def abort ( self, status: int, reason: str | None = None ) -> NoReturn:
        raise self._handler.faults.status(status, reason)
