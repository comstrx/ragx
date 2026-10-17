from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.enums import Role


@dataclass(frozen=True, slots=True)
class User:

    id         : UUID
    name       : str
    email      : str | None
    role       : Role
    created_at : datetime
    updated_at : datetime
    deleted_at : datetime | None = None

    def is_staff ( self ) -> bool:
        return Role(self.role).is_staff()
