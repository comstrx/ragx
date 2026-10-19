from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from core.array import array
from core.error import Code, Fault
import sqlalchemy as sa
from .session import Row
from .model import Model, Relation

type Related = Callable[[type[Model]], Any]
type Fetch = Callable[[Any], Awaitable[list[Row]]]

class Loader:

    def __init__ ( self, model: type[Model], related: Related, fetch: Fetch ) -> None:

        self._model   = model
        self._related = related
        self._fetch   = fetch

    async def load ( self, found: Sequence[Model], names: Sequence[str] ) -> None:

        if not found: return

        for name in names: await self.relate(found, name, self._model.relation_named(name))

    async def relate ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        match relation.kind:
            case "belongs_to": await self.belongs_to(found, name, relation)
            case "has_one" | "has_many": await self.has(found, name, relation)
            case "belongs_to_many": await self.belongs_to_many(found, name, relation)
            case "morph_many": await self.morph_many(found, name, relation)
            case "morph_to": await self.morph_to(found, name, relation)
            case _: raise Fault(Code.INTERNAL, reason=f"relation.{relation.kind}")

    def query ( self, relation: Relation ) -> Any:

        return self._related(self._model.resolve(relation.related or ""))

    async def belongs_to ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        related = self._model.resolve(relation.related or "")
        foreign = relation.foreign or related.foreign_name()
        keys    = { getattr(item, foreign) for item in found if getattr(item, foreign) is not None }
        owners  = await self.query(relation).where_in(relation.local, keys).get() if keys else []
        by_key  = { getattr(owner, relation.local): owner for owner in owners }

        for item in found: item.attach(name, by_key.get(getattr(item, foreign)))

    async def has ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        foreign  = relation.foreign or self._model.foreign_name()
        keys     = { getattr(item, relation.local) for item in found }
        children = await self.query(relation).where_in(foreign, keys).get()
        grouped  = array.group(children, lambda child: getattr(child, foreign))

        for item in found:

            own = grouped.get(getattr(item, relation.local), [])

            item.attach(name, own if relation.kind == "has_many" else (own[0] if own else None))

    async def belongs_to_many ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        related = self._model.resolve(relation.related or "")
        mine    = relation.pivot_foreign or self._model.foreign_name()
        theirs  = relation.pivot_related or related.foreign_name()
        keys    = { getattr(item, relation.local) for item in found }
        bridge  = sa.table(relation.pivot or "", sa.column(mine), sa.column(theirs))
        links   = await self._fetch(sa.select(bridge).where(bridge.c[mine].in_(list(keys))))
        wanted  = { link[theirs] for link in links }
        others  = await self.query(relation).where_in(related.primary, wanted).get() if wanted else []
        by_key  = { getattr(other, related.primary): other for other in others }
        grouped: dict[Any, list[Any]] = {}

        for link in links:

            other = by_key.get(link[theirs])

            if other is not None: grouped.setdefault(link[mine], []).append(other)

        for item in found: item.attach(name, grouped.get(getattr(item, relation.local), []))

    async def morph_many ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        prefix   = relation.morph or ""
        keys     = { getattr(item, relation.local) for item in found }
        query    = self.query(relation).where(f"{prefix}_type", self._model.morph_name)
        children = await query.where_in(f"{prefix}_id", keys).get()
        grouped  = array.group(children, lambda child: getattr(child, f"{prefix}_id"))

        for item in found: item.attach(name, grouped.get(getattr(item, relation.local), []))

    async def morph_to ( self, found: Sequence[Model], name: str, relation: Relation ) -> None:

        prefix  = relation.morph or ""
        by_type = array.group(found, lambda item: str(getattr(item, f"{prefix}_type")))
        owners: dict[tuple[str, Any], Any] = {}

        for alias, items in by_type.items():

            model = next((entry for entry in Model.registry.values() if entry.morph_name == alias), None)

            if model is None: raise Fault(Code.INTERNAL, reason=f"morph.{alias}")

            keys  = { getattr(item, f"{prefix}_id") for item in items }
            heads = await self._related(model).where_in(model.primary, keys).get()

            owners.update({ (alias, getattr(head, model.primary)): head for head in heads })

        for item in found:

            mark = (str(getattr(item, f"{prefix}_type")), getattr(item, f"{prefix}_id"))

            item.attach(name, owners.get(mark))
