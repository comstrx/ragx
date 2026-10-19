from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from core.database import Model, Relation, morph_to
from core.date import DateTime, date
from core.rand import Uuid
from app.enums import Table

@dataclass(frozen=True, slots=True, kw_only=True)
class Token(Model):

    table     : ClassVar[str] = Table.TOKENS
    soft      : ClassVar[bool] = False
    relations : ClassVar[Mapping[str, Relation]] = { "owner": morph_to("owner") }

    id         : Uuid
    owner_type : str
    owner_id   : Uuid
    kind       : str
    hash       : str
    expires_at : DateTime
    revoked_at : DateTime | None = None
    created_at : DateTime
    updated_at : DateTime

    def alive ( self ) -> bool:

        return self.revoked_at is None and date.utc(self.expires_at) > date.now()
