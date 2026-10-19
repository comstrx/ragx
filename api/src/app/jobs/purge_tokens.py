from typing import override
from core.queue import Queued
from app.repositories import tokens
from app.utils.cycle import Job

class PurgeTokens(Job, Queued):

    queue = "maintenance"

    @override
    async def handle ( self ) -> None:

        removed = await tokens.purge()

        self.log.info("tokens.purged", removed=removed)
