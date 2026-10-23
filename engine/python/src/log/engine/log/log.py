from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from engine.context import context
from structlog import PrintLoggerFactory, WriteLoggerFactory, configure, get_logger, make_filtering_bound_logger
from structlog.processors import StackInfoRenderer, TimeStamper, add_log_level, format_exc_info
from structlog.typing import EventDict, Processor, WrappedLogger
from .logger import LEVELS, Fields, Logger, Render, elapsed
import logging

class Log:

    name = "app"

    def __init__ ( self ) -> None:

        self._sink: TextIO | None = None
        self._level    = "info"
        self._renderer = "console"
        self._file: Path | None = None
        self._render   = Render()
        self._taps: list[list[EventDict]] = []

    def setup ( self, level: str = "info", renderer: str = "console", file: Path | None = None ) -> None:

        processors: list[Processor] = [
            self._render.correlate, self._render.redact, add_log_level, TimeStamper(fmt="iso", utc=True),
            StackInfoRenderer(), format_exc_info, self._tap_, self._render.renderer(renderer, colors=file is None),
        ]

        configure(
            processors=processors,
            wrapper_class=make_filtering_bound_logger(self.level_of(level)),
            logger_factory=self._factory_(file),
            cache_logger_on_first_use=True,
        )

        self._level    = level.lower()
        self._renderer = renderer
        self._file     = file

    def level_of ( self, level: str ) -> int:

        chosen = level.upper()

        if chosen.lower() not in LEVELS: chosen = "INFO"

        return logging.getLevelNamesMapping()[chosen]

    def level ( self ) -> str:

        return self._level

    def enabled ( self, level: str ) -> bool:

        return self.level_of(level) >= self.level_of(self._level)

    def describe ( self ) -> dict[str, object]:

        return { "level": self._level, "renderer": self._renderer, "file": str(self._file) if self._file else None }

    def get ( self, name: str | None = None ) -> Logger:

        return Logger(get_logger(name or self.name))

    def bind ( self, **fields: Any ) -> Logger:

        return self.get().bind(**fields)

    def share ( self, **fields: Any ) -> None:

        context.put(**fields)

    def unshare ( self, *names: str ) -> None:

        context.forget(*names)

    def shared ( self ) -> dict[str, Any]:

        return context.snapshot()

    def debug ( self, event: str, **fields: Any ) -> None:

        self.get().debug(event, **fields)

    def info ( self, event: str, **fields: Any ) -> None:

        self.get().info(event, **fields)

    def warning ( self, event: str, **fields: Any ) -> None:

        self.get().warning(event, **fields)

    def error ( self, event: str, **fields: Any ) -> None:

        self.get().error(event, **fields)

    def critical ( self, event: str, **fields: Any ) -> None:

        self.get().critical(event, **fields)

    def exception ( self, event: str, **fields: Any ) -> None:

        self.get().exception(event, **fields)

    def at ( self, level: str, event: str, **fields: Any ) -> None:

        self.get().at(level, event, **fields)

    @contextmanager
    def span ( self, event: str, level: str = "info", **fields: Any ) -> Iterator[Fields]:

        with self.get().span(event, level, **fields) as extra: yield extra

    @contextmanager
    def capture ( self ) -> Iterator[list[EventDict]]:

        events: list[EventDict] = []

        self._taps.append(events)

        try: yield events
        finally: self._taps.remove(events)

    def ms ( self, started: float ) -> float:

        return elapsed(started)

    def close ( self ) -> None:

        if self._sink is not None: self._sink.close()

        self._sink = None

    def _tap_ ( self, _: WrappedLogger, __: str, event: EventDict ) -> EventDict:

        for tap in self._taps: tap.append(dict(event))

        return event

    def _factory_ ( self, file: Path | None ) -> Any:

        self.close()

        if file is None: return PrintLoggerFactory()

        file.parent.mkdir(parents=True, exist_ok=True)

        self._sink = file.open("a", encoding="utf-8")

        return WriteLoggerFactory(file=self._sink)
