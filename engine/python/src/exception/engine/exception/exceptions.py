from collections.abc import Awaitable, Callable, Mapping
from typing import Any, ClassVar

from engine.error import Code, Fault
from engine.log import log
import time

type Mapper = Callable[[BaseException], Fault]
type Target = Code | Mapper
type Facts = Mapping[str, object]
type Reporter = Callable[[BaseException, Fault, Mapping[str, object]], Any]
type Callback = Callable[[BaseException], Any]
KEYS = 1024

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

class Exceptions:

    def __init__ ( self ) -> None:

        self._handler = Handler()
        self._reporters: list[Reporter] = []
        self._callbacks: dict[type[BaseException], list[Callback]] = {}
        self._limit   = 0
        self._window  = 60.0
        self._seen: dict[str, tuple[float, int]] = {}
        self._dropped = 0

    def use ( self, handler: Handler ) -> None:

        self._handler = handler

    def handler ( self ) -> Handler:

        return self._handler

    def map ( self, kind: type[BaseException], target: Target ) -> None:

        self._handler.map(kind, target)

    def silence ( self, *kinds: type[BaseException] ) -> None:

        self._handler.silence(*kinds)

    def level ( self, kind: type[BaseException], level: str ) -> None:

        self._handler.level(kind, level)

    def reportable ( self, kind: type[BaseException], callback: Callback ) -> None:

        self._callbacks.setdefault(kind, []).append(callback)

    def on_report ( self, reporter: Reporter ) -> None:

        if reporter not in self._reporters: self._reporters.append(reporter)

    def throttle ( self, limit: int, window: float = 60.0 ) -> None:

        self._limit  = max(limit, 0)
        self._window = max(window, 0.001)

        self._seen.clear()

    def fault_of ( self, error: BaseException ) -> Fault:

        return self._handler.fault_of(error)

    def handle ( self, error: BaseException, **facts: object ) -> Fault:

        fault = self._handler.fault_of(error)

        self.report(error, fault, **facts)

        return fault

    def report ( self, error: BaseException, fault: Fault | None = None, **facts: object ) -> bool:

        chosen = fault or self._handler.fault_of(error)

        if self._handler.quiet(error) or not self._admit_(error, chosen): return False

        self._handler.report(error, chosen, facts)

        for kind in type(error).__mro__:

            for callback in self._callbacks.get(kind, ()): self._safely_(callback, error)

        for reporter in self._reporters:

            try: reporter(error, chosen, facts)
            except Exception as failure: log.warning("exception.reporter_failed", kind=type(failure).__name__)

        return True

    def guard[T] ( self, work: Callable[[], T], default: T, **facts: object ) -> T:

        try: return work()
        except Exception as error:

            self.handle(error, **facts)

            return default

    async def rescue[T] ( self, work: Callable[[], Awaitable[T]], default: T, **facts: object ) -> T:

        try: return await work()
        except Exception as error:

            self.handle(error, **facts)

            return default

    def wrap ( self, error: BaseException, code: Code = Code.INTERNAL ) -> Fault:

        found = self._handler.target_of(error)

        return self._handler.fault_of(error) if found is not None or isinstance(error, Fault) else Fault.of(error, code)

    def dropped ( self ) -> int:

        return self._dropped

    def describe ( self ) -> dict[str, object]:

        return {
            **self._handler.describe(), "handler": type(self._handler).__name__, "reporters": len(self._reporters),
            "callbacks": sorted(kind.__name__ for kind in self._callbacks), "throttle": self._limit,
            "dropped": self._dropped,
        }

    def _admit_ ( self, error: BaseException, fault: Fault ) -> bool:

        if self._limit <= 0: return True

        key   = f"{type(error).__name__}:{fault.reason}"
        now   = time.monotonic()
        start, count = self._seen.get(key, (now, 0))

        if now - start >= self._window: start, count = now, 0
        if len(self._seen) >= KEYS and key not in self._seen: self._seen.clear()

        self._seen[key] = (start, count + 1)

        if count < self._limit: return True

        self._dropped += 1

        return False

    def _safely_ ( self, callback: Callback, error: BaseException ) -> None:

        try: callback(error)
        except Exception as failure: log.warning("exception.reporter_failed", kind=type(failure).__name__)
