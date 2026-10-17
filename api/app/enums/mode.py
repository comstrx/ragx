from enum import StrEnum


class Mode(StrEnum):

    LOCAL      = "local"
    TESTING    = "testing"
    PRODUCTION = "production"

    def is_local ( self ) -> bool:
        return self is Mode.LOCAL

    def is_production ( self ) -> bool:
        return self is Mode.PRODUCTION
