from collections.abc import Iterable
from typing import Any

from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.typing import EventDict, Processor, WrappedLogger
from core.context import context
import orjson

SECRETS = ("password", "secret", "token", "authorization", "cookie", "api_key", "apikey", "credential", "private_key")
MASK    = "***"
SCHEME  = "://"
SLOTS   = ("tenant", "user", "job", "task", "event")

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
