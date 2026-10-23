from collections.abc import Iterable, Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any, Self

from engine.context import context
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger
import orjson, time

SECRETS = ("password", "secret", "token", "authorization", "cookie", "api_key", "apikey", "credential", "private_key")
MASK    = "***"
SCHEME  = "://"
SLOTS   = ("tenant", "user", "job", "task", "event")
type Fields = MutableMapping[str, Any]
LEVELS = ("debug", "info", "warning", "error", "critical")

def masked_url ( text: str ) -> str:

    start = text.find(SCHEME)
    end   = text.find("@", start + len(SCHEME)) if start >= 0 else -1
    colon = text.find(":", start + len(SCHEME), end) if end > 0 else -1

    if colon < 0 or "/" in text[start + len(SCHEME):end]: return text

    return f"{text[:colon + 1]}{MASK}{text[end:]}"

def masked ( value: Any, key: str = "" ) -> Any:

    if any(mark in key.lower() for mark in SECRETS) and value not in (None, ""): return MASK
    if isinstance(value, str): return masked_url(value) if SCHEME in value else value
    if isinstance(value, dict): return { name: masked(item, str(name)) for name, item in value.items() }
    if isinstance(value, list | tuple): return [masked(item) for item in value]

    return value

def serialize ( event: EventDict, **_: Any ) -> str:

    return orjson.dumps(event, default=str).decode()

class Render:

    def correlate ( self, _: WrappedLogger, __: str, event: EventDict ) -> EventDict:

        request_id = context.request_id()

        if request_id: event.setdefault("request_id", request_id)

        for name, value in context.snapshot().items():

            if name in SLOTS: event.setdefault(name, value)

        return event

    def redact ( self, _: WrappedLogger, __: str, event: EventDict ) -> EventDict:

        for key in list(event):

            if key != "event": event[key] = masked(event[key], key)

        return event

    def renderer ( self, kind: str, colors: bool ) -> Processor:

        if kind == "json": return JSONRenderer(serializer=serialize)

        return ConsoleRenderer(colors=colors)

    def drop ( self, names: Iterable[str] ) -> Processor:

        hidden = set(names)

        def processor ( _: WrappedLogger, __: str, event: EventDict ) -> EventDict:

            for name in hidden: event.pop(name, None)

            return event

        return processor

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
