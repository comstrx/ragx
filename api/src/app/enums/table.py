from enum import StrEnum

class Table(StrEnum):

    ROLES     = "roles"
    USERS     = "users"
    ROLE_USER = "role_user"
    TOKENS    = "tokens"

    def primary ( self ) -> str:
        return "id"
