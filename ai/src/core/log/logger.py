from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, Self

from structlog.typing import FilteringBoundLogger
import time

type Fields = MutableMapping[str, Any]

LEVELS = ("debug", "info", "warning", "error", "critical")

class Logger:

    __slots__ = ("_bound", "_fields")

    def __init__ ( self, bound: FilteringBoundLogger, fields: dict[str, Any] | None = None ) -> None:

        self._bound  = bound
        self._fields = dict(fields or {})

    def bind ( self, **fields: Any ) -> Self:

        return type(self)(self._bound.bind(**fields), { **self._fields, **fields })

    def unbind ( self, *names: str ) -> Self:

        kept = { name: value for name, value in self._fields.items() if name not in names }

        return type(self)(self._bound.unbind(*[name for name in names if name in self._fields]), kept)

    def fields ( self ) -> dict[str, Any]:

        return dict(self._fields)

    def debug ( self, event: str, **fields: Any ) -> None:

        self._bound.debug(event, **fields)

    def info ( self, event: str, **fields: Any ) -> None:

        self._bound.info(event, **fields)

    def warning ( self, event: str, **fields: Any ) -> None:

        self._bound.warning(event, **fields)

    def error ( self, event: str, **fields: Any ) -> None:

        self._bound.error(event, **fields)

    def critical ( self, event: str, **fields: Any ) -> None:

        self._bound.critical(event, **fields)

    def exception ( self, event: str, **fields: Any ) -> None:

        self._bound.exception(event, **fields)

    def at ( self, level: str, event: str, **fields: Any ) -> None:

        chosen = level.lower()

        if chosen not in LEVELS: chosen = "info"

        getattr(self._bound, chosen)(event, **fields)

    @contextmanager
    def span ( self, event: str, level: str = "info", **fields: Any ) -> Iterator[Fields]:

        started = time.perf_counter()
        extra: Fields = {}

        try: yield extra
        except BaseException as error:

            self._bound.error(
                event, ms=elapsed(started), outcome="failed", error=type(error).__name__, **fields, **extra,
            )

            raise

        self.at(level, event, ms=elapsed(started), **fields, **extra)

def elapsed ( started: float ) -> float:

    return round((time.perf_counter() - started) * 1000, 2)
