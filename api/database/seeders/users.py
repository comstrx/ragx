from core.database import Database, Statement
from app.enums import Role, Table
from app.support.dna import identity


class UsersSeeder:

    name = "users"
    rows = (("World", Role.CLIENT),)

    async def run ( self, database: Database ) -> None:

        for name, role in self.rows:

            await database.execute(Statement(
                f'INSERT INTO "{Table.USERS}" ("id", "name", "role") VALUES ($1, $2, $3::role) '
                'ON CONFLICT DO NOTHING',
                (identity.new(), name, role.value),
            ))
