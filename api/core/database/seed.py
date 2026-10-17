from collections.abc import Sequence
from typing import Protocol

from core.date import date
from core.log import log
from .database import Database


class Seeder(Protocol):

    name: str

    async def run ( self, database: Database ) -> None: ...


class Seeds:

    def __init__ ( self, database: Database, seeders: Sequence[Seeder] ) -> None:

        self._database = database
        self._seeders  = tuple(seeders)

    def names ( self ) -> list[str]:
        return [seeder.name for seeder in self._seeders]

    async def run ( self, only: Sequence[str] = () ) -> list[str]:

        done: list[str] = []

        for seeder in self._seeders:

            if only and seeder.name not in only: continue

            started = date.tick()

            await seeder.run(self._database)

            done.append(seeder.name)
            log.info("database.seeded", seeder=seeder.name, ms=date.elapsed(started))

        return done
