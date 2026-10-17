from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from core.database import Model, Relation, belongs_to_many
from core.date import DateTime
from core.rand import Uuid
from app.enums import Table

@dataclass(frozen=True, slots=True, kw_only=True)
class Role(Model):

    table     : ClassVar[str] = Table.ROLES
    relations : ClassVar[Mapping[str, Relation]] = {
        "users": belongs_to_many("User", Table.ROLE_USER, foreign="role_id", related_key="user_id"),
    }

    id         : Uuid
    name       : str
    label      : str
    created_at : DateTime
    updated_at : DateTime
    deleted_at : DateTime | None = None

    def is_admin ( self ) -> bool:
        return self.name == "admin"
