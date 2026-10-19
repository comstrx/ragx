from core.rand import Uuid
from app.models import User
from app.utils.cycle import Repository
from app.utils.dna import identity

class UserRepository(Repository[User]):

    model = User

    async def find_by_email ( self, email: str, *relations: str ) -> User | None:

        return await self.first_by("email", email.strip().lower(), *relations)

    async def find_by_name ( self, name: str ) -> User | None:

        return await self.first_by("name", name)

    async def taken ( self, email: str ) -> bool:

        return await self.query().where("email", email.strip().lower()).exists()

    async def assign ( self, user: Uuid | str, role: Uuid | str ) -> None:

        await self.query().pivot("roles").attach(identity.parse(user), identity.parse(role))

    async def with_roles ( self, key: Uuid | str ) -> User | None:

        return await self.find(key, "roles")
