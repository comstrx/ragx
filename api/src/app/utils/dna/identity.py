from core.error import Code, Fault
from core.rand import Uuid, rand

class Identity:

    def new ( self ) -> Uuid:

        return rand.uuid()

    def parse ( self, value: object, field: str = "id" ) -> Uuid:

        if isinstance(value, Uuid): return value

        try: return Uuid(str(value))
        except (TypeError, ValueError) as error:
            raise Fault(Code.BAD_REQUEST, reason=field, errors={ field: ["Expected an id"] }) from error

    def text ( self, value: Uuid ) -> str:

        return str(value)
