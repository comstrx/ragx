from core.error import Code, Fault
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError, SQLAlchemyError, TimeoutError as PoolTimeout
import asyncio

CONFLICT    = ("23505",)
REFERENCE   = ("23503",)
VALIDATION  = ("23502", "23514", "22")
CONNECTION  = ("08", "53", "57P")

class Translate:

    def fault ( self, error: BaseException ) -> Fault:

        match error:
            case Fault(): return error
            case PoolTimeout() | OperationalError() | InterfaceError():
                return Fault(Code.UNAVAILABLE, reason="database")
            case DBAPIError(): return self._dbapi_(error)
            case OSError() | asyncio.TimeoutError() | TimeoutError(): return Fault(Code.UNAVAILABLE, reason="database")
            case SQLAlchemyError(): return Fault(Code.INTERNAL, reason="database")
            case _: return Fault(Code.INTERNAL, reason="database")

    def state ( self, error: DBAPIError ) -> str:

        origin = error.orig

        return str(getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None) or "")

    def origins ( self, error: DBAPIError ) -> tuple[object, ...]:

        origin = error.orig

        return (origin, getattr(origin, "__cause__", None))

    def detail ( self, error: DBAPIError, name: str ) -> str | None:

        for origin in self.origins(error):

            value = getattr(origin, name, None)

            if value: return str(value)

        return None

    def constraint ( self, error: DBAPIError ) -> str | None:

        for name in ("constraint_name", "column_name", "table_name"):

            value = self.detail(error, name)

            if value: return value

        return None

    def _dbapi_ ( self, error: DBAPIError ) -> Fault:

        state = self.state(error)
        name  = self.constraint(error)

        if state.startswith(CONFLICT): return Fault(Code.CONFLICT, reason=name)
        if state.startswith(REFERENCE): return Fault(Code.BAD_REQUEST, reason=name)
        if state.startswith(VALIDATION): return Fault(Code.VALIDATION, reason=name, errors=self._errors_(error))
        if state.startswith(CONNECTION) or error.connection_invalidated:
            return Fault(Code.UNAVAILABLE, reason="database")

        return Fault(Code.INTERNAL, reason="database")

    def _errors_ ( self, error: DBAPIError ) -> dict[str, list[str]] | None:

        column = self.detail(error, "column_name")

        return { column: [Code.VALIDATION.message()] } if column else None
