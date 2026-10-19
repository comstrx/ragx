from typing import Annotated

from fastapi import Body, Depends, File, Form, Header, Path, Query, Request, UploadFile as Upload
from starlette.responses import (
    FileResponse as Served, HTMLResponse as Html, PlainTextResponse as Text, RedirectResponse as Redirect,
    StreamingResponse as Streamed,
)

from .app import App, Http, Lifespan, throttle
from .docs import Docs, Documented
from .envelope import Envelope
from .facts import Facts
from .request import Payload
from .response import Response
from .route import Bound, Group, Guard, Handler, Route
from .router import Router
from .server import Server
from .sse import EventStream, Packet, Sse
from .throttle import Throttle, by_client
from .trace import Trace
from .warm import Warm

type Incoming = Annotated[Payload, Depends(Payload.of)]

http   = Http()
server = Server()
warm   = Warm()

__all__ = [
    "App", "Body", "Bound", "Depends", "Docs", "Documented", "Envelope", "EventStream", "Facts", "File", "Form",
    "Group", "Guard", "Handler", "Header", "Html", "Http", "Incoming", "Lifespan", "Packet", "Path", "Payload", "Query",
    "Redirect", "Request", "Response", "Route", "Router", "Served", "Server", "Sse", "Streamed", "Text", "Throttle",
    "Trace", "Upload", "Warm", "by_client", "http", "server", "throttle", "warm",
]
