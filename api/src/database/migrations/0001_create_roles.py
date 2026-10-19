from core.database import Blueprint, Schema
from app.enums import Table

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("name", 60).unique()
            table.string("label", 120)
            table.timestamps()
            table.soft_deletes()

        await schema.create(Table.ROLES, define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(Table.ROLES)
