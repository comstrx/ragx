from core.queue import Queued
from app.repositories import tokens
from app.utils.bases import BaseJob

class PurgeTokens(BaseJob, Queued):

    queue = "maintenance"

    async def handle ( self ) -> None:

        removed = await tokens.purge()

        self.log.info("tokens.purged", removed=removed)
