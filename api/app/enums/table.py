from enum import StrEnum


class Table(StrEnum):

    USERS = "users"

    def primary ( self ) -> str:
        return "id"
