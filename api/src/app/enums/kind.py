from enum import StrEnum, unique
from typing import assert_never

@unique
class TokenKind(StrEnum):

    ACCESS  = "access"
    REFRESH = "refresh"

    def stored ( self ) -> bool:

        match self:
            case TokenKind.ACCESS:  return False
            case TokenKind.REFRESH: return True
            case _:                 assert_never(self)
