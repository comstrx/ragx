from structlog.stdlib import BoundLogger as Logger

from .log import Log

log = Log()

__all__ = ["Log", "Logger", "log"]
