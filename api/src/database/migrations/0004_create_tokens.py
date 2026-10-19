from core.database import Blueprint, Schema
from app.enums import Table, TokenKind

class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.morphs("owner")
            table.enum("kind", TokenKind, kind="token_kind")
            table.string("hash", 128).unique()
            table.timestamp("expires_at").index()
            table.timestamp("revoked_at").nullable()
            table.timestamps()

        await schema.create(Table.TOKENS, define)

    async def down ( self, schema: Schema ) -> None:

        await schema.drop(Table.TOKENS)
