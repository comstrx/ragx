from functools import cached_property

from core.log import Logger, log

class BaseService:

    @cached_property
    def log ( self ) -> Logger:
        return log.bind(service=type(self).__name__)
