from collections.abc import AsyncIterator
from pathlib import Path

from core.error import Code, Fault
from .base import Pathish
from .dir import Dir
from .driver import Driver, transfer
from .file import File
from .path import Paths

class LocalDriver:

    def __init__ ( self, root: Path, url: str | None = None ) -> None:

        self._root  = root.resolve()
        self._url   = url.rstrip("/") if url else None
        self._file  = File()
        self._dir   = Dir()
        self._paths = Paths()

    def root ( self ) -> Path:
        return self._root

    def resolve ( self, path: str ) -> Path:

        target = (self._root / path).resolve()

        if not self._paths.within(self._root, target): raise Fault(Code.BAD_REQUEST, reason="storage.path")

        return target

    async def put ( self, path: str, data: bytes, _mime: str ) -> int:

        await self._file.write_bytes(self.resolve(path), data)

        return len(data)

    async def get ( self, path: str ) -> bytes:
        return await self._file.read_bytes(self.resolve(path))

    async def stream ( self, path: str ) -> AsyncIterator[bytes]:

        target = self.resolve(path)

        if not await self._file.exists(target): raise Fault(Code.NOT_FOUND, reason=path)

        return self._file.chunks(target)

    async def exists ( self, path: str ) -> bool:
        return await self._file.exists(self.resolve(path))

    async def size ( self, path: str ) -> int:
        return await self._file.size(self.resolve(path))

    async def modified ( self, path: str ) -> float:
        return await self._file.modified(self.resolve(path))

    async def delete ( self, path: str ) -> bool:

        target = self.resolve(path)

        return await self._file.remove(target) or await self._dir.remove(target)

    async def copy ( self, source: str, target: str ) -> None:
        await self._file.copy(self.resolve(source), self.resolve(target))

    async def move ( self, source: str, target: str ) -> None:
        await self._file.move(self.resolve(source), self.resolve(target))

    async def list ( self, prefix: str = "" ) -> list[str]:

        base = self.resolve(prefix) if prefix else self._root

        if not await self._dir.exists(base): return []

        found = [path async for path in self._dir.walk(base)]

        return sorted(path.relative_to(self._root).as_posix() for path in found)

    def url ( self, path: str ) -> str | None:
        return f"{self._url}/{path}" if self._url else None

    async def temporary_url ( self, path: str, _seconds: int ) -> str | None:
        return self.url(path)

    def local ( self, path: str ) -> Path | None:
        return self.resolve(path)

    async def upload ( self, source: Pathish, path: str, mime: str | None = None ) -> int:
        return await transfer.upload(self, source, path, mime)

    async def download ( self, path: str, target: Pathish ) -> int:
        return await transfer.download(self, path, target)

    async def remove ( self, path: str ) -> bool:
        return await self.delete(path)

    async def sync ( self, other: Driver, prefix: str = "" ) -> int:
        return await transfer.sync(self, other, prefix)
