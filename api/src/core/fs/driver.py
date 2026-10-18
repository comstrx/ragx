from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from .base import Pathish
from .file import File

class Driver(Protocol):

    async def put ( self, path: str, data: bytes, mime: str ) -> int: ...

    async def get ( self, path: str ) -> bytes: ...

    async def stream ( self, path: str ) -> AsyncIterator[bytes]: ...

    async def exists ( self, path: str ) -> bool: ...

    async def size ( self, path: str ) -> int: ...

    async def modified ( self, path: str ) -> float: ...

    async def delete ( self, path: str ) -> bool: ...

    async def copy ( self, source: str, target: str ) -> None: ...

    async def move ( self, source: str, target: str ) -> None: ...

    async def list ( self, prefix: str = "" ) -> list[str]: ...

    def url ( self, path: str ) -> str | None: ...

    async def temporary_url ( self, path: str, seconds: int ) -> str | None: ...

    def local ( self, path: str ) -> Path | None: ...

    async def upload ( self, source: Pathish, path: str, mime: str | None = None ) -> int: ...

    async def download ( self, path: str, target: Pathish ) -> int: ...

    async def remove ( self, path: str ) -> bool: ...

    async def sync ( self, other: Driver, prefix: str = "" ) -> int: ...

class Transfer:

    def __init__ ( self ) -> None:

        self._file = File()

    async def upload ( self, driver: Driver, source: Pathish, path: str, mime: str | None = None ) -> int:
        return await driver.put(path, await self._file.read_bytes(source), self._file.mime(source, mime))

    async def download ( self, driver: Driver, path: str, target: Pathish ) -> int:
        return await self._file.write_stream(target, await driver.stream(path))

    async def sync ( self, origin: Driver, mirror: Driver, prefix: str = "" ) -> int:

        copied = 0

        for path in await origin.list(prefix):

            if await mirror.exists(path) and await mirror.size(path) == await origin.size(path): continue

            await mirror.put(path, await origin.get(path), self._file.mime(path))

            copied += 1

        return copied

transfer = Transfer()
