from core.database import Database
from app.enums import Role
from app.repositories import roles, users

class UsersSeeder:

    name = "users"
    rows = (("World", "world@ragx.test", Role.CLIENT),)

    async def run ( self, _database: Database ) -> None:

        for name, email, role in self.rows:

            fresh  = { "name": name, "email": email, "password": None }
            user   = await users.find_by_email(email) or await users.create(fresh)
            member = await roles.ensure(role.value, role.label())

            await users.assign(user.id, member.id)
