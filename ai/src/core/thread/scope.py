from types import TracebackType
from core.error import Code, Fault
import asyncio

class Mutex:

    def __init__ ( self ) -> None:

        self._lock = asyncio.Lock()

    async def __aenter__ ( self ) -> None:

        await self._lock.acquire()

    async def __aexit__ (
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None,
    ) -> None:

        self._lock.release()

class Deadline:

    def __init__ ( self, seconds: float, reason: str = "timeout" ) -> None:

        self._seconds = seconds
        self._reason = reason
        self._scope: asyncio.Timeout | None = None

    async def __aenter__ ( self ) -> None:

        self._scope = asyncio.timeout(self._seconds)
        await self._scope.__aenter__()

    async def __aexit__ (
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None,
    ) -> bool | None:

        if self._scope is None: return None
        try: await self._scope.__aexit__(kind, error, traceback)
        except TimeoutError as timeout:
            raise Fault(Code.UNAVAILABLE, reason=self._reason, unknown=True) from timeout
        return None
