from engine.database import Schema, outbox

TABLE = "outbox"

class Migration:

    async def up ( self, schema: Schema ) -> None:

        await schema.create(TABLE, outbox.define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(TABLE)
