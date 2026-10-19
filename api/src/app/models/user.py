from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from core.database import Model, Relation, belongs_to_many, morph_many
from core.date import DateTime
from core.rand import Uuid
from app.enums import Table

@dataclass(frozen=True, slots=True, kw_only=True)
class User(Model):

    table     : ClassVar[str] = Table.USERS
    relations : ClassVar[Mapping[str, Relation]] = {
        "roles"  : belongs_to_many("Role", Table.ROLE_USER, foreign="user_id", related_key="role_id"),
        "tokens" : morph_many("Token", "owner"),
    }

    id         : Uuid
    name       : str
    email      : str
    password   : str | None
    created_at : DateTime
    updated_at : DateTime
    deleted_at : DateTime | None = None

    def role_names ( self ) -> list[str]:

        return [str(role.name) for role in self.related.get("roles", [])]

    def has_role ( self, name: str ) -> bool:

        return name in self.role_names()
