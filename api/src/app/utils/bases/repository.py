from collections.abc import Mapping

from core.array import Page
from core.database import Model, Query, database
from core.rand import Uuid
from app.utils.dna import identity

class BaseRepository[M: Model]:

    model : type[M]

    def query ( self ) -> Query[M]:
        return Query(self.model, database)

    async def find ( self, key: Uuid | str, *relations: str ) -> M | None:
        return await self.query().with_(*relations).find(identity.parse(key))

    async def one ( self, key: Uuid | str, *relations: str ) -> M:
        return await self.query().with_(*relations).find_or_fail(identity.parse(key))

    async def first_by ( self, column: str, value: object, *relations: str ) -> M | None:
        return await self.query().with_(*relations).where(column, value).first()

    async def all ( self, page: int = 1, limit: int = 20, *relations: str ) -> tuple[list[M], Page]:
        return await self.query().with_(*relations).latest().paginate(page, limit)

    async def count ( self ) -> int:
        return await self.query().count()

    async def create ( self, values: Mapping[str, object] ) -> M:
        return await self.query().create(values)

    async def update ( self, key: Uuid | str, values: Mapping[str, object] ) -> M:

        await self.query().where(self.model.primary, identity.parse(key)).update(values)

        return await self.one(key)

    async def delete ( self, key: Uuid | str ) -> bool:
        return await self.query().where(self.model.primary, identity.parse(key)).delete() == 1

    async def restore ( self, key: Uuid | str ) -> bool:
        return await self.query().where(self.model.primary, identity.parse(key)).restore() == 1
