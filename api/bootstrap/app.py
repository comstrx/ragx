from pathlib import Path

from core.database import database
from core.http import App, http
from core.log import log
from config import AppConfig, DatabaseConfig, LogConfig
from routes import api, docs
from .boot import Boot


class Application:

    root = Path(__file__).resolve().parents[1]

    def settings ( self ) -> AppConfig:
        return AppConfig.load(self.root)

    def logging ( self ) -> LogConfig:
        return LogConfig.load(self.root)

    def storage ( self ) -> DatabaseConfig:
        return DatabaseConfig.load(self.root)

    def boot ( self ) -> Boot:
        return Boot(self.root, database, self.storage())

    def create ( self ) -> App:

        settings = self.settings()
        logging  = self.logging()

        log.setup(level=logging.level, renderer=logging.renderer)

        facts = { "version": settings.version, "release": settings.release, "env": settings.env }

        return http.build(
            settings.name, settings.version, [api.routes, docs.routes],
            debug=settings.debug, facts=facts, origins=settings.origins, lifespan=self.boot().lifespan,
        )
