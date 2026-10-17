from core.database import Database
from app.enums import Role
from app.repositories import roles

class RolesSeeder:

    name = "roles"

    async def run ( self, _database: Database ) -> None:

        for role in Role: await roles.ensure(role.value, role.label())
