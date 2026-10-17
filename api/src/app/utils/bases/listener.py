from typing import Any

from core.log import Logger, log

class BaseListener:

    async def handle ( self, _event: Any ) -> None:
        return None

    @property
    def log ( self ) -> Logger:
        return log.bind(listener=type(self).__name__)
