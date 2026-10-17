from enum import StrEnum


class Message(StrEnum):

    HELLO = "Hello {name}"

    def render ( self, **fields: str ) -> str:
        return self.value.format(**fields)
