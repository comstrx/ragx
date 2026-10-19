from enum import StrEnum
from typing import Self, assert_never

class Role(StrEnum):

    ADMIN  = "admin"
    CLIENT = "client"

    def label ( self ) -> str:

        match self:
            case Role.ADMIN:  return "Administrator"
            case Role.CLIENT: return "Client"
            case _:           assert_never(self)

    def is_staff ( self ) -> bool:

        return self is Role.ADMIN

    @classmethod
    def default ( cls ) -> Self:

        return cls(cls.CLIENT)
