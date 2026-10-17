from asyncpg import exceptions as pg
from core.error import Code, Fault
import asyncio


class Translate:

    def fault ( self, error: BaseException ) -> Fault:

        match error:
            case Fault(): return error
            case pg.UniqueViolationError(): return Fault(Code.CONFLICT, reason=self._name_(error))
            case pg.ForeignKeyViolationError(): return Fault(Code.BAD_REQUEST, reason=self._name_(error))
            case pg.NotNullViolationError() | pg.CheckViolationError() | pg.DataError():
                return Fault(Code.VALIDATION, reason=self._name_(error), errors=self._errors_(error))
            case pg.TooManyConnectionsError() | pg.CannotConnectNowError() | pg.PostgresConnectionError():
                return Fault(Code.UNAVAILABLE, reason="database")
            case pg.InterfaceError() | OSError() | asyncio.TimeoutError() | TimeoutError():
                return Fault(Code.UNAVAILABLE, reason="database")
            case _: return Fault(Code.INTERNAL, reason="database")

    def _name_ ( self, error: BaseException ) -> str | None:

        if not isinstance(error, pg.PostgresError): return None

        return error.constraint_name or error.column_name or error.table_name or None

    def _errors_ ( self, error: BaseException ) -> dict[str, list[str]] | None:

        column = error.column_name if isinstance(error, pg.PostgresError) else None

        return { column: [Code.VALIDATION.message()] } if column else None
