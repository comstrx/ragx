from core.database import Schema, outbox
from app.enums import Table

class Migration:

    async def up ( self, schema: Schema ) -> None:

        await schema.create(Table.OUTBOX, outbox.define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(Table.OUTBOX)
