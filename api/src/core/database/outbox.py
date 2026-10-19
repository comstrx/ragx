from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from core.context import context
from core.date import date
from core.error import Code, Fault
from core.json import json
from core.log import log
from core.rand import Uuid, rand
from .blueprint import Blueprint
from .engine import Database
from .session import Row
import asyncio, contextlib
import sqlalchemy as sa

type Deliver = Callable[[Mapping[str, Any]], Awaitable[object]]

GRACE   = 10.0
LEASE   = 30.0
BATCH   = 100
CEILING = 300.0
BACKOFF = 1.0
EVERY   = 1.0

def shaped ( name: str ) -> sa.TableClause:

    return sa.table(
        name, sa.column("id", sa.Uuid()), sa.column("kind", sa.String()), sa.column("payload", sa.Text()),
        sa.column("attempts", sa.Integer()), sa.column("error", sa.Text()),
        sa.column("available_at", sa.DateTime(timezone=True)), sa.column("created_at", sa.DateTime(timezone=True)),
    )

class Outbox:

    def __init__ (
        self, database: Database, table: str = "outbox", grace: float = GRACE, lease: float = LEASE,
        backoff: float = BACKOFF,
    ) -> None:

        self._database = database
        self._grace    = grace
        self._lease    = lease
        self._backoff  = backoff
        self._table    = shaped(table)
        self._kinds    : dict[str, Deliver] = {}
        self._task     : asyncio.Task[None] | None = None
        self._halt     = asyncio.Event()
        self._sent     = 0
        self._failed   = 0
        self._relayed  = 0

    def setup ( self, table: str | None = None, grace: float | None = None, lease: float | None = None ) -> None:

        if table is not None: self._table = shaped(table)
        if grace is not None: self._grace = grace
        if lease is not None: self._lease = lease

    @staticmethod
    def define ( table: Blueprint ) -> None:

        table.id()
        table.string("kind", 120)
        table.text("payload")
        table.integer("attempts").default(0)
        table.text("error").nullable()
        table.timestamp("available_at")
        table.timestamp("created_at").default(sa.func.now())
        table.index(["available_at"])

    def kind ( self, name: str, deliver: Deliver ) -> None:

        self._kinds[name] = deliver

    def kinds ( self ) -> list[str]:

        return sorted(self._kinds)

    def deliverer ( self, kind: str ) -> Deliver:

        found = self._kinds.get(kind)

        if found is None: raise Fault(Code.INTERNAL, reason="outbox.kind")

        return found

    async def put ( self, kind: str, payload: Mapping[str, Any] ) -> bool:

        deliver = self.deliverer(kind)
        session = self._database.current()

        if session is None:

            await deliver(payload)

            return False

        key  = rand.uuid()
        now  = date.now()
        body = json.dumps(dict(payload))
        row  = { "id": key, "kind": kind, "payload": body, "attempts": 0, "created_at": now }

        await session.execute(sa.insert(self._table).values(**row, available_at=date.add(now, seconds=self._grace)))
        await context.defer(lambda: self.flush(key, kind, body, 0))

        return True

    async def flush ( self, key: Uuid, kind: str, body: str, attempts: int ) -> bool:

        try: await self.deliverer(kind)(json.loads(body))
        except Exception as error:

            await self.later(key, attempts + 1, error)

            return False

        await self._database.execute(sa.delete(self._table).where(self._table.c.id == key))

        self._sent += 1

        return True

    async def later ( self, key: Uuid, attempts: int, error: Exception ) -> None:

        pause = min(self._backoff * 2.0 ** (attempts - 1), CEILING)
        due   = date.add(date.now(), seconds=pause)
        kind  = type(error).__name__

        self._failed += 1

        log.warning("outbox.retry", id=str(key), attempts=attempts, error=kind, pause=pause)

        table = self._table

        await self._database.execute(
            sa.update(table).where(table.c.id == key).values(attempts=attempts, error=kind, available_at=due),
        )

    async def relay ( self, limit: int = BATCH ) -> int:

        table = self._table
        now   = date.now()
        due   = sa.select(table.c.id).where(table.c.available_at <= now).order_by(table.c.available_at).limit(limit)
        claim = sa.update(table).where(table.c.id.in_(due.with_for_update(skip_locked=True))).values(
            available_at=date.add(now, seconds=self._lease),
        ).returning(table.c.id, table.c.kind, table.c.payload, table.c.attempts)
        rows  = await self._database.fetch(claim)

        delivered = [await self.redeliver(row) for row in rows]

        self._relayed += sum(delivered)

        return sum(delivered)

    async def redeliver ( self, row: Row ) -> bool:

        return await self.flush(row["id"], str(row["kind"]), str(row["payload"]), int(row["attempts"]))

    async def pending ( self ) -> int:

        found = await self._database.value(sa.select(sa.func.count()).select_from(self._table))

        return int(found or 0)

    def start ( self, every: float = EVERY ) -> bool:

        if self._task is not None and not self._task.done(): return False

        self._halt.clear()
        self._task = asyncio.create_task(self.loop(every), name="outbox:relay")

        return True

    async def loop ( self, every: float ) -> None:

        while not self._halt.is_set():

            try: await self.relay()
            except Fault as fault: log.warning("outbox.relay_failed", reason=fault.reason)

            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(every): await self._halt.wait()

    async def stop ( self, wait: float = 5.0 ) -> bool:

        task, self._task = self._task, None

        if task is None: return False

        self._halt.set()

        try:
            async with asyncio.timeout(wait): await task
        except TimeoutError: task.cancel()

        return True

    def describe ( self ) -> dict[str, Any]:

        return {
            "kinds": self.kinds(), "sent": self._sent, "failed": self._failed, "relayed": self._relayed,
            "running": self._task is not None and not self._task.done(), "grace": self._grace, "lease": self._lease,
        }
