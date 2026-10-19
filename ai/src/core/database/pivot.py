from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any

from core.error import Code, Fault
import sqlalchemy as sa
from .model import Model
from .session import Session

type Work = Callable[[Session], Awaitable[Any]]
type Runner = Callable[[Work], Awaitable[Any]]

class Pivot:

    __slots__ = ("_owner", "_related", "_run", "_table")

    def __init__ ( self, model: type[Model], name: str, run: Runner ) -> None:

        relation = model.relation_named(name)

        if relation.kind != "belongs_to_many" or not relation.pivot:
            raise Fault(Code.INTERNAL, reason=f"database.pivot.{name}")

        related       = model.resolve(relation.related or "")
        self._owner   = relation.pivot_foreign or model.foreign_name()
        self._related = relation.pivot_related or related.foreign_name()
        self._table   = relation.pivot
        self._run     = run

    def table ( self, *extra: str ) -> sa.TableClause:

        return sa.table(self._table, *(sa.column(name) for name in (self._owner, self._related, *extra)))

    async def keys ( self, owner: object ) -> list[Any]:

        pivot     = self.table()
        statement = sa.select(pivot.c[self._related]).where(pivot.c[self._owner] == owner)
        rows      = await self._run(lambda session: session.fetch(statement))

        return [row[self._related] for row in rows]

    async def has ( self, owner: object, related: object ) -> bool:

        return str(related) in { str(key) for key in await self.keys(owner) }

    async def attach ( self, owner: object, *related: object, values: Mapping[str, object] | None = None ) -> int:

        known   = { str(key) for key in await self.keys(owner) }
        fresh   = list(dict.fromkeys(item for item in related if str(item) not in known))
        extra   = dict(values or {})
        pivot   = self.table(*extra)
        payload = [{ self._owner: owner, self._related: item, **extra } for item in fresh]

        if not payload: return 0

        return int(await self._run(lambda session: session.execute(sa.insert(pivot).values(payload))))

    async def detach ( self, owner: object, *related: object ) -> int:

        pivot     = self.table()
        statement = sa.delete(pivot).where(pivot.c[self._owner] == owner)

        if related: statement = statement.where(pivot.c[self._related].in_(list(related)))

        return int(await self._run(lambda session: session.execute(statement)))

    async def sync ( self, owner: object, related: Iterable[object], detaching: bool = True ) -> dict[str, list[str]]:

        wanted  = { str(item): item for item in related }
        known   = { str(key): key for key in await self.keys(owner) }
        missing = [wanted[key] for key in wanted if key not in known]
        extra   = [known[key] for key in known if key not in wanted] if detaching else []

        await self.attach(owner, *missing)

        if extra: await self.detach(owner, *extra)

        return { "attached": sorted(str(item) for item in missing), "detached": sorted(str(item) for item in extra) }

    async def toggle ( self, owner: object, *related: object ) -> dict[str, list[str]]:

        known   = { str(key) for key in await self.keys(owner) }
        present = [item for item in related if str(item) in known]
        absent  = [item for item in related if str(item) not in known]

        if present: await self.detach(owner, *present)

        await self.attach(owner, *absent)

        return { "attached": sorted(str(item) for item in absent), "detached": sorted(str(item) for item in present) }
