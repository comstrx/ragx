from core.date import DateTime, date
from core.rand import Uuid
from app.enums import TokenKind
from app.models import Token, User
from app.utils.bases import BaseRepository

class TokenRepository(BaseRepository[Token]):

    model = Token

    async def remember ( self, user: User, kind: TokenKind, fingerprint: str, expires_at: DateTime ) -> Token:

        return await self.create({
            "owner_type" : User.morph_name,
            "owner_id"   : user.id,
            "kind"       : kind.value,
            "hash"       : fingerprint,
            "expires_at" : expires_at,
        })

    async def alive ( self, fingerprint: str, kind: TokenKind ) -> Token | None:

        found = await self.query().where("hash", fingerprint).where("kind", kind.value).where_null("revoked_at").first()

        return found if found is not None and found.alive() else None

    async def revoke ( self, key: Uuid | str ) -> bool:
        return await self.query().where("id", key).where_null("revoked_at").update({ "revoked_at": date.now() }) == 1

    async def revoke_all ( self, user: User ) -> int:

        return await self.query() \
            .where("owner_type", User.morph_name).where("owner_id", user.id).where_null("revoked_at") \
            .update({ "revoked_at": date.now() })

    async def purge ( self ) -> int:
        return await self.query().where("expires_at", "<", date.now()).force_delete()
