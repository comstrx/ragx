from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from structlog import PrintLoggerFactory, WriteLoggerFactory, configure, make_filtering_bound_logger
from structlog.processors import StackInfoRenderer, TimeStamper, add_log_level, format_exc_info
from structlog.stdlib import BoundLogger, get_logger
from structlog.typing import Processor
from core.context import context
from .render import Render
import logging, time

type Fields = MutableMapping[str, Any]

LEVELS = ("debug", "info", "warning", "error", "critical")

class Log:

    name = "app"

    def __init__ ( self ) -> None:

        self._sink: TextIO | None = None
        self._level    = "info"
        self._renderer = "console"
        self._file: Path | None = None
        self._render   = Render()

    def setup ( self, level: str = "info", renderer: str = "console", file: Path | None = None ) -> None:

        processors: list[Processor] = [
            self._render.correlate, self._render.redact, add_log_level, TimeStamper(fmt="iso", utc=True),
            StackInfoRenderer(), format_exc_info, self._render.renderer(renderer, colors=file is None),
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

    def _factory_ ( self, file: Path | None ) -> Any:

        if self._sink is not None: self._sink.close()

        self._sink = None

        if file is None: return PrintLoggerFactory()

        file.parent.mkdir(parents=True, exist_ok=True)

        self._sink = file.open("a", encoding="utf-8")

        return WriteLoggerFactory(file=self._sink)

    def level_of ( self, level: str ) -> int:
        return logging.getLevelNamesMapping()[level.upper()]

    def level ( self ) -> str:
        return self._level

    def enabled ( self, level: str ) -> bool:
        return self.level_of(level) >= self.level_of(self._level)

    def describe ( self ) -> dict[str, object]:
        return { "level": self._level, "renderer": self._renderer, "file": str(self._file) if self._file else None }

    def get ( self, name: str | None = None ) -> BoundLogger:
        return get_logger(name or self.name)

    def share ( self, **fields: Any ) -> None:

        for name, value in fields.items(): context.set(name, value)

    def unshare ( self, *names: str ) -> None:

        for name in names: context.clear(name)

    def shared ( self ) -> dict[str, Any]:
        return context.snapshot()

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

    def critical ( self, event: str, **fields: Any ) -> None:
        self.get().critical(event, **fields)

    def exception ( self, event: str, **fields: Any ) -> None:
        self.get().exception(event, **fields)

    def at ( self, level: str, event: str, **fields: Any ) -> None:
        getattr(self.get(), level.lower())(event, **fields)

    @contextmanager
    def span ( self, event: str, level: str = "info", **fields: Any ) -> Iterator[Fields]:

        started = time.perf_counter()
        extra: Fields = {}

        try: yield extra
        except BaseException:

            self.get().error(event, ms=self.ms(started), outcome="failed", **fields, **extra)

            raise

        self.at(level, event, ms=self.ms(started), **fields, **extra)

    def ms ( self, started: float ) -> float:
        return round((time.perf_counter() - started) * 1000, 2)
