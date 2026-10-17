from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

from structlog import configure, make_filtering_bound_logger
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer, StackInfoRenderer, TimeStamper, add_log_level, format_exc_info
from structlog.stdlib import BoundLogger, get_logger
from structlog.typing import EventDict, Processor, WrappedLogger
from core.context import context
import logging, orjson, time

type Fields = MutableMapping[str, Any]


class Log:

    name = "app"

    def setup ( self, level: str = "info", renderer: str = "console" ) -> None:

        render: Processor = JSONRenderer(serializer=self._json_) if renderer == "json" else ConsoleRenderer()
        processors: list[Processor] = [
            self._correlate_, add_log_level, TimeStamper(fmt="iso", utc=True),
            StackInfoRenderer(), format_exc_info, render,
        ]

        configure(
            processors=processors,
            wrapper_class=make_filtering_bound_logger(self._level_(level)),
            cache_logger_on_first_use=True,
        )

    def get ( self, name: str | None = None ) -> BoundLogger:
        return get_logger(name or self.name)

    def bind ( self, **fields: Any ) -> BoundLogger:
        return self.get().bind(**fields)

    def debug ( self, event: str, **fields: Any ) -> None:
        self.get().debug(event, **fields)

    def info ( self, event: str, **fields: Any ) -> None:
        self.get().info(event, **fields)

    def warning ( self, event: str, **fields: Any ) -> None:
        self.get().warning(event, **fields)

    def error ( self, event: str, **fields: Any ) -> None:
        self.get().error(event, **fields)

    def exception ( self, event: str, **fields: Any ) -> None:
        self.get().exception(event, **fields)

    @contextmanager
    def span ( self, event: str, **fields: Any ) -> Iterator[Fields]:

        started = time.perf_counter()
        extra: Fields = {}

        try: yield extra
        except BaseException:

            self.get().error(event, ms=self._ms_(started), outcome="failed", **fields, **extra)

            raise

        self.get().info(event, ms=self._ms_(started), **fields, **extra)

    def _ms_ ( self, started: float ) -> float:
        return round((time.perf_counter() - started) * 1000, 2)

    def _level_ ( self, level: str ) -> int:
        return logging.getLevelNamesMapping()[level.upper()]

    def _json_ ( self, event: Fields, **_: Any ) -> str:
        return orjson.dumps(event, default=str).decode()

    def _correlate_ ( self, _: WrappedLogger, __: str, event: EventDict ) -> EventDict:

        request_id = context.request_id()
        if request_id: event.setdefault("request_id", request_id)

        return event
