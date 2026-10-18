from structlog.stdlib import BoundLogger as Logger

from .log import Log
from .render import Render, masked, masked_url

log = Log()

__all__ = ["Log", "Logger", "Render", "log", "masked", "masked_url"]
