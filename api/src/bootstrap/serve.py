from core.http import server
from .app import Application

class Serve:

    target = "bootstrap:application"

    def run ( self ) -> None:

        application = Application()
        settings    = application.settings()
        logging     = application.logging()

        server.run(
            self.target, host=settings.host, port=settings.port, workers=settings.workers,
            reload=settings.debug, level=logging.level,
        )
