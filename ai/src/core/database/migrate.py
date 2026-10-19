from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Protocol, TypedDict

from core.date import date
from core.error import Code, Fault
from core.log import log
import sqlalchemy as sa
from .engine import Database
from .session import Session
from .blueprint import Blueprint
from .schema import Schema

LOCK     = 7_201_441
TEMPLATE = """from core.database import Blueprint, Schema

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.timestamps()

        await schema.create("{table}", define)

    async def down ( self, schema: Schema ) -> None:
        await schema.drop("{table}")
"""

class Status(TypedDict):

    applied : list[str]
    pending : list[str]
    batch   : int

class Migration(Protocol):

    async def up ( self, schema: Schema ) -> None: ...

    async def down ( self, schema: Schema ) -> None: ...

class Migrator:

    def __init__ ( self, database: Database, folder: Path, table: str = "schema_migrations" ) -> None:

        self.table     = table
        self._database = database
        self._folder   = folder
        self._ledger   = sa.table(table, sa.column("name"), sa.column("batch"), sa.column("applied_at"))

    def files ( self ) -> list[Path]:

        return sorted(path for path in self._folder.glob("*.py") if path.is_file() and not path.name.startswith("_"))

    def next_number ( self ) -> int:

        numbers = [int(path.stem.split("_", 1)[0]) for path in self.files() if path.stem.split("_", 1)[0].isdigit()]

        return max(numbers, default=0) + 1

    def make ( self, name: str, table: str | None = None ) -> Path:

        slug   = "".join(char if char.isalnum() else "_" for char in name.strip().lower()).strip("_")
        target = self._folder / f"{self.next_number():04d}_{slug}.py"

        if target.exists(): raise Fault(Code.CONFLICT, reason=target.name)

        self._folder.mkdir(parents=True, exist_ok=True)
        target.write_text(TEMPLATE.format(table=table or slug.removeprefix("create_")))

        return target

    def load ( self, path: Path ) -> Migration:

        spec = spec_from_file_location(f"migrations.{path.stem}", path)

        if spec is None or spec.loader is None: raise Fault(Code.INTERNAL, reason=f"migration.{path.name}")

        module = module_from_spec(spec)

        spec.loader.exec_module(module)

        kind = getattr(module, "Migration", None)

        if kind is None: raise Fault(Code.INTERNAL, reason=f"migration.{path.name}.class")

        instance: Migration = kind()

        return instance

    async def applied ( self ) -> dict[str, int]:

        async with self._database.transaction() as session:

            await self._prepare_(session)

            listing = sa.select(self._ledger.c.name, self._ledger.c.batch).order_by(self._ledger.c.name)
            found   = await session.fetch(listing)

        return { str(row["name"]): int(row["batch"]) for row in found }

    async def pending ( self ) -> list[Path]:

        done = await self.applied()

        return [path for path in self.files() if path.stem not in done]

    async def apply ( self ) -> list[str]:

        applied: list[str] = []

        async with self._database.transaction() as session:

            await session.lock(LOCK)
            await self._prepare_(session)

            done   = { str(row["name"]) for row in await session.fetch(sa.select(self._ledger.c.name)) }
            latest = await session.value(sa.select(sa.func.coalesce(sa.func.max(self._ledger.c.batch), 0)))
            batch  = int(latest or 0) + 1
            schema = Schema(session)

            for path in self.files():

                if path.stem in done: continue

                started = date.tick()

                await self.load(path).up(schema)
                record = sa.insert(self._ledger).values(name=path.stem, batch=batch, applied_at=date.now())

                await session.execute(record)

                applied.append(path.stem)
                log.info("database.migrated", migration=path.stem, batch=batch, ms=date.elapsed(started))

        return applied

    async def rollback ( self, steps: int = 1 ) -> list[str]:

        reverted: list[str] = []

        async with self._database.transaction() as session:

            await session.lock(LOCK)
            await self._prepare_(session)

            recent  = sa.select(self._ledger.c.batch).distinct().order_by(self._ledger.c.batch.desc()).limit(steps)
            batches = await session.fetch(recent)
            schema  = Schema(session)
            byname  = { path.stem: path for path in self.files() }

            for batch in [int(row["batch"]) for row in batches]:

                within = sa.select(self._ledger.c.name).where(self._ledger.c.batch == batch)
                names  = await session.fetch(within.order_by(self._ledger.c.name.desc()))

                for name in [str(row["name"]) for row in names]:

                    path = byname.get(name)

                    if path is None: raise Fault(Code.INTERNAL, reason=f"migration.{name}.missing")

                    await self.load(path).down(schema)
                    await session.execute(sa.delete(self._ledger).where(self._ledger.c.name == name))

                    reverted.append(name)
                    log.info("database.rolled_back", migration=name, batch=batch)

        return reverted

    async def reset ( self ) -> list[str]:

        done = await self.applied()

        return await self.rollback(len(set(done.values()))) if done else []

    async def fresh ( self ) -> list[str]:

        await self.reset()

        return await self.apply()

    async def status ( self ) -> Status:

        done    = await self.applied()
        pending = [path.stem for path in self.files() if path.stem not in done]

        return Status(applied=sorted(done), pending=pending, batch=max(done.values(), default=0))

    async def _prepare_ ( self, session: Session ) -> None:

        def define ( table: Blueprint ) -> None:

            table.string("name", 160).key()
            table.integer("batch")
            table.timestamp("applied_at").default(sa.func.now())

        await Schema(session).create(self.table, define)
