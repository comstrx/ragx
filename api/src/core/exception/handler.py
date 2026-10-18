from collections.abc import Callable, Mapping
from typing import Any, ClassVar, NoReturn

from core.error import Code, Errors, Fault, Faults
from core.log import log

type Mapper = Callable[[BaseException], Fault]
type Facts = Mapping[str, object]
type Reporter = Callable[[BaseException, Fault, Facts], Any]

class Handler:

    maps   : ClassVar[Mapping[type[BaseException], Code | Mapper]] = {}
    silent : ClassVar[tuple[type[BaseException], ...]] = ()
    levels : ClassVar[Mapping[type[BaseException], str]] = {}
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

    def level_of ( self, error: BaseException ) -> str | None:
        return next((level for kind, level in self.levels.items() if isinstance(error, kind)), None)

    def report ( self, error: BaseException, fault: Fault, facts: Facts ) -> None:

        if isinstance(error, self.silent): return

        level = self.level_of(error)

        if level is not None:

            log.at(level, "exception.handled", kind=type(error).__name__, code=fault.code, reason=fault.reason, **facts)

            return

        if fault.server():

            log.exception(
                "exception.unhandled", kind=type(error).__name__, code=fault.code, reason=fault.reason, **facts,
            )

            return

        log.debug("exception.handled", code=fault.code, reason=fault.reason, **facts)

class Exceptions:

    def __init__ ( self ) -> None:

        self._handler  = Handler()
        self._reporters: list[Reporter] = []

    def use ( self, handler: Handler ) -> None:
        self._handler = handler

    def handler ( self ) -> Handler:
        return self._handler

    def on_report ( self, reporter: Reporter ) -> None:

        if reporter not in self._reporters: self._reporters.append(reporter)

    def fault_of ( self, error: BaseException ) -> Fault:
        return self._handler.fault_of(error)

    def handle ( self, error: BaseException, **facts: object ) -> Fault:

        fault = self._handler.handle(error, **facts)

        for reporter in self._reporters: reporter(error, fault, facts)

        return fault

    def throw (
        self, code: Code, message: str | None = None, reason: str | None = None, errors: Errors | None = None,
    ) -> NoReturn:
        raise Fault(code, message, reason, errors)

    def abort ( self, status: int, reason: str | None = None ) -> NoReturn:
        raise self._handler.faults.status(status, reason)

    def guard[T] ( self, work: Callable[[], T], default: T, **facts: object ) -> T:

        try: return work()
        except Exception as error:

            self.handle(error, **facts)

            return default
