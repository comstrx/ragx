from collections.abc import AsyncIterator
from pathlib import Path

from core.exceptions import Code, Fault
from core.fs import fs

CHUNK = 64 * 1024

class LocalDisk:

    def __init__ ( self, name: str, root: Path, url: str | None = None ) -> None:

        self._name = name
        self._root = root.resolve()
        self._url  = url.rstrip("/") if url else None

    @property
    def name ( self ) -> str:
        return self._name

    def root ( self ) -> Path:
        return self._root

    def resolve ( self, path: str ) -> Path:

        target = (self._root / path).resolve()

        if not fs.within(self._root, target): raise Fault(Code.BAD_REQUEST, reason="storage.path")

        return target

    async def put ( self, path: str, data: bytes, _mime: str ) -> int:

        await fs.write_bytes(self.resolve(path), data)

        return len(data)

    async def get ( self, path: str ) -> bytes:
        return await fs.read_bytes(self.resolve(path))

    async def stream ( self, path: str ) -> AsyncIterator[bytes]:

        target = self.resolve(path)

        if not await fs.is_file(target): raise Fault(Code.NOT_FOUND, reason=path)

        return self._chunks_(target)

    async def _chunks_ ( self, target: Path ) -> AsyncIterator[bytes]:

        data = await fs.read_bytes(target)

        for start in range(0, len(data), CHUNK): yield data[start:start + CHUNK]

    async def exists ( self, path: str ) -> bool:
        return await fs.is_file(self.resolve(path))

    async def size ( self, path: str ) -> int:

        target = self.resolve(path)

        if not await fs.is_file(target): raise Fault(Code.NOT_FOUND, reason=path)

        return await fs.size(target)

    async def delete ( self, path: str ) -> bool:
        return await fs.remove(self.resolve(path))

    async def copy ( self, source: str, target: str ) -> None:
        await fs.copy(self.resolve(source), self.resolve(target))

    async def move ( self, source: str, target: str ) -> None:
        await fs.move(self.resolve(source), self.resolve(target))

    async def list ( self, prefix: str = "" ) -> list[str]:

        base = self.resolve(prefix) if prefix else self._root

        if not await fs.is_dir(base): return []

        found = [path async for path in fs.walk(base) if path.is_file()]

        return sorted(path.relative_to(self._root).as_posix() for path in found)

    def url ( self, path: str ) -> str | None:
        return f"{self._url}/{path}" if self._url else None

    async def temporary_url ( self, path: str, _seconds: int ) -> str | None:
        return self.url(path)

    def local ( self, path: str ) -> Path | None:
        return self.resolve(path)
