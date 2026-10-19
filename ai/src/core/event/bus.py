from collections.abc import Awaitable, Callable
from typing import Any, Protocol
import asyncio

type Envelope = dict[str, Any]
type Handler = Callable[[Envelope], Awaitable[None]]

class Bus(Protocol):

    @property
    def name ( self ) -> str: ...

    @property
    def local ( self ) -> bool: ...

    async def publish ( self, envelope: Envelope ) -> None: ...

    async def consume ( self, handler: Handler, stop: asyncio.Event ) -> None: ...

    async def close ( self ) -> None: ...

class LocalBus:

    name  = "local"
    local = True

    async def publish ( self, _envelope: Envelope ) -> None:

        return None

    async def consume ( self, _handler: Handler, stop: asyncio.Event ) -> None:

        await stop.wait()

    async def close ( self ) -> None:

        return None
