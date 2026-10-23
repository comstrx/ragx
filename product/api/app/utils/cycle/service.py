from engine.log import Logger, log

class Service:

    @property
    def log ( self ) -> Logger:

        return log.bind(service=type(self).__name__)
