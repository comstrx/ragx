from app.models import Role
from app.utils.cycle import Repository

class RoleRepository(Repository[Role]):

    model = Role

    async def by_name ( self, name: str ) -> Role | None:

        return await self.first_by("name", name)

    async def ensure ( self, name: str, label: str ) -> Role:

        found = await self.by_name(name)

        return found if found is not None else await self.create({ "name": name, "label": label })
