from core.database import Blueprint, Schema
from app.enums import Table

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.foreign("role_id", Table.ROLES)
            table.foreign("user_id", Table.USERS)
            table.timestamps()
            table.unique(["role_id", "user_id"])

        await schema.create(Table.ROLE_USER, define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(Table.ROLE_USER)
