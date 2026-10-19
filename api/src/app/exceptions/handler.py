from collections.abc import Mapping
from typing import ClassVar, override

from core.error import Code, Fault
from core.exception import Handler, Mapper

type Mapped = Mapping[type[BaseException], Code | Mapper]

SERVER_ERROR = 500

class ExceptionHandler(Handler):

    maps : ClassVar[Mapped] = {
        ValueError        : Code.BAD_REQUEST,
        KeyError          : Code.NOT_FOUND,
        PermissionError   : Code.FORBIDDEN,
        TimeoutError      : Code.UNAVAILABLE,
        NotImplementedError: Code.INTERNAL,
    }
    silent : ClassVar[tuple[type[BaseException], ...]] = ()

    @override
    def report ( self, error: BaseException, fault: Fault, facts: Mapping[str, object] ) -> None:

        if isinstance(error, Fault) and fault.status < SERVER_ERROR: return

        super().report(error, fault, facts)
