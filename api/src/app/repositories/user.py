from core.database import database
from core.rand import Uuid
from app.enums import Table
from app.models import User
from app.utils.bases import BaseRepository
from app.utils.dna import identity
import sqlalchemy as sa

class UserRepository(BaseRepository[User]):

    model = User
    pivot = sa.table(
        Table.ROLE_USER, sa.column("role_id"), sa.column("user_id"), sa.column("created_at"), sa.column("updated_at"),
    )

    async def find_by_email ( self, email: str, *relations: str ) -> User | None:
        return await self.first_by("email", email.strip().lower(), *relations)

    async def find_by_name ( self, name: str ) -> User | None:
        return await self.first_by("name", name)

    async def taken ( self, email: str ) -> bool:
        return await self.query().where("email", email.strip().lower()).exists()

    async def assign ( self, user: Uuid | str, role: Uuid | str ) -> None:

        owner  = identity.parse(user)
        member = identity.parse(role)
        bound  = (self.pivot.c.user_id == owner, self.pivot.c.role_id == member)
        known  = sa.select(sa.func.count()).select_from(self.pivot).where(*bound)

        if int(await database.value(known) or 0): return

        await database.execute(sa.insert(self.pivot).values(user_id=owner, role_id=member))

    async def with_roles ( self, key: Uuid | str ) -> User | None:
        return await self.find(key, "roles")
