from uuid import UUID, uuid7

from core.error import Code, Fault


class Identity:

    def new ( self ) -> UUID:
        return uuid7()

    def parse ( self, value: object, field: str = "id" ) -> UUID:

        if isinstance(value, UUID): return value

        try: return UUID(str(value))
        except (TypeError, ValueError) as error:
            raise Fault(Code.BAD_REQUEST, reason=field, errors={ field: ["Expected an id"] }) from error

    def text ( self, value: UUID ) -> str:
        return str(value)
