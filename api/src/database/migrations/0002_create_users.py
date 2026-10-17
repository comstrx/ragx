from core.database import Blueprint, Schema
from app.enums import Table

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("name", 120)
            table.string("email", 254)
            table.string("password", 255).nullable()
            table.timestamps()
            table.soft_deletes()
            table.unique(["lower(email)"], name="users_email_alive", where="deleted_at IS NULL")
            table.index("created_at")

        await schema.create(Table.USERS, define)

    async def down ( self, schema: Schema ) -> None:
        await schema.drop(Table.USERS)
