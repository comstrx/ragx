from collections.abc import Mapping

from core.database import Database
from app.support.bases import BaseService


class HealthService(BaseService):

    def __init__ ( self, database: Database ) -> None:

        super().__init__()

        self._database = database

    async def status ( self, facts: Mapping[str, object] ) -> tuple[bool, dict[str, object]]:

        alive = await self._database.ping()

        return alive, {
            "status"   : "ok" if alive else "degraded",
            "version"  : facts.get("version"),
            "release"  : facts.get("release"),
            "database" : { "alive": alive, **self._database.describe() },
        }
