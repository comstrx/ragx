from collections.abc import Callable, Mapping
from typing import Any, ClassVar

from core.error import Code, Fault
from core.log import log

type Mapper = Callable[[BaseException], Fault]
type Target = Code | Mapper
type Facts = Mapping[str, object]

class Handler:

    maps   : ClassVar[Mapping[type[BaseException], Target]] = {}
    silent : ClassVar[tuple[type[BaseException], ...]] = ()
    levels : ClassVar[Mapping[type[BaseException], str]] = {}

    def __init__ ( self ) -> None:

        self._maps: dict[type[BaseException], Target] = dict(type(self).maps)
        self._silent: set[type[BaseException]] = set(type(self).silent)
        self._levels: dict[type[BaseException], str] = dict(type(self).levels)

    def map ( self, kind: type[BaseException], target: Target ) -> None:

        self._maps[kind] = target

    def silence ( self, *kinds: type[BaseException] ) -> None:

        self._silent.update(kinds)

    def level ( self, kind: type[BaseException], level: str ) -> None:

        self._levels[kind] = level

    def target_of ( self, error: BaseException ) -> Target | None:

        return next((self._maps[kind] for kind in type(error).__mro__ if kind in self._maps), None)

    def fault_of ( self, error: BaseException ) -> Fault:

        if isinstance(error, Fault): return error

        target = self.target_of(error)

        if target is None: return Fault.of(error, Code.INTERNAL, "unexpected")

        fault = Fault(target) if isinstance(target, Code) else target(error)

        if fault.__cause__ is None: fault.__cause__ = error

        return fault

    def level_of ( self, error: BaseException ) -> str | None:

        return next((self._levels[kind] for kind in type(error).__mro__ if kind in self._levels), None)

    def quiet ( self, error: BaseException ) -> bool:

        return any(kind in self._silent for kind in type(error).__mro__)

    def handle ( self, error: BaseException, **facts: object ) -> Fault:

        fault = self.fault_of(error)

        self.report(error, fault, facts)

        return fault

    def report ( self, error: BaseException, fault: Fault, facts: Facts ) -> None:

        if self.quiet(error): return

        fields: dict[str, Any] = { "kind": type(error).__name__, "code": fault.code, "reason": fault.reason, **facts }
        level = self.level_of(error)

        if level is not None: log.at(level, "exception.handled", **fields)
        elif fault.server(): log.get().exception("exception.unhandled", exc_info=error, **fields)
        else: log.debug("exception.handled", **fields)

    def describe ( self ) -> dict[str, object]:

        return {
            "maps"   : sorted(kind.__name__ for kind in self._maps),
            "silent" : sorted(kind.__name__ for kind in self._silent),
            "levels" : { kind.__name__: level for kind, level in self._levels.items() },
        }
