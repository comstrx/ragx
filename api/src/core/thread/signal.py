from collections.abc import Awaitable, Callable

from core.log import log
import asyncio, contextlib, signal

type Hook = Callable[[], Awaitable[None] | None]

SIGNALS = (signal.SIGTERM, signal.SIGINT)

class Shutdown:

    def __init__ ( self ) -> None:

        self._event: asyncio.Event | None = None
        self._hooks: list[Hook] = []
        self._installed = False
        self._reason    = ""

    def event ( self ) -> asyncio.Event:

        if self._event is None: self._event = asyncio.Event()

        return self._event

    def install ( self ) -> bool:

        if self._installed: return False

        loop = asyncio.get_running_loop()

        for sig in SIGNALS:

            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.trigger, sig.name)

        self._installed = True

        return True

    def on ( self, hook: Hook ) -> None:

        if hook not in self._hooks: self._hooks.append(hook)

    def trigger ( self, reason: str = "requested" ) -> None:

        if self.event().is_set(): return

        self._reason = reason

        log.info("shutdown.triggered", reason=reason)
        self.event().set()

    def triggered ( self ) -> bool:
        return self._event is not None and self._event.is_set()

    def reason ( self ) -> str:
        return self._reason

    async def wait ( self ) -> str:

        await self.event().wait()

        return self._reason

    async def drain ( self, wait: float = 10.0 ) -> int:

        done = 0

        for hook in reversed(self._hooks):

            try:

                async with asyncio.timeout(wait):

                    result = hook()

                    if result is not None: await result

                done += 1

            except Exception: log.exception("shutdown.hook_failed", hook=getattr(hook, "__qualname__", "hook"))

        return done

    def reset ( self ) -> None:

        self._event     = None
        self._hooks     = []
        self._installed = False
        self._reason    = ""
