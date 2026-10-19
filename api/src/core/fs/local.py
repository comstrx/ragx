from collections.abc import AsyncIterator
from pathlib import Path
from typing import ClassVar, override

from core.error import Code, Fault
from .dir import Dir
from .driver import CORE, PATH, Driver
from .file import File
from .path import Paths
import builtins

class LocalDriver(Driver):

    name         = "local"
    capabilities : ClassVar[frozenset[str]] = CORE | {PATH}

    def __init__ ( self, root: Path, url: str | None = None ) -> None:

        super().__init__(url)

        self._root  = root.resolve()
        self._file  = File()
        self._dir   = Dir()
        self._paths = Paths()

    def root ( self ) -> Path:

        return self._root

    def resolve ( self, path: str ) -> Path:

        target = (self._root / path).resolve()

        if not self._paths.within(self._root, target): raise Fault(Code.BAD_REQUEST, reason="fs.path")

        return target

    @override
    async def put ( self, path: str, data: bytes, _mime: str ) -> int:

        await self._file.write_bytes(self.resolve(path), data)

        return len(data)

    @override
    async def get ( self, path: str ) -> bytes:

        return await self._file.read_bytes(self.resolve(path))

    @override
    async def stream ( self, path: str ) -> AsyncIterator[bytes]:

        target = self.resolve(path)

        if not await self._file.exists(target): raise Fault(Code.NOT_FOUND, reason="fs.missing")

        return self._file.chunks(target)

    @override
    async def exists ( self, path: str ) -> bool:

        return await self._file.exists(self.resolve(path))

    @override
    async def size ( self, path: str ) -> int:

        return await self._file.size(self.resolve(path))

    @override
    async def modified ( self, path: str ) -> float:

        return await self._file.modified(self.resolve(path))

    @override
    async def delete ( self, path: str ) -> bool:

        target = self.resolve(path)

        return await self._file.remove(target) or await self._dir.remove(target)

    @override
    async def copy ( self, source: str, target: str ) -> None:

        await self._file.copy(self.resolve(source), self.resolve(target))

    @override
    async def move ( self, source: str, target: str ) -> None:

        await self._file.move(self.resolve(source), self.resolve(target))

    @override
    async def list ( self, prefix: str = "" ) -> builtins.list[str]:

        base = self.resolve(prefix) if prefix else self._root

        if not await self._dir.exists(base): return []

        found = [path async for path in self._dir.walk(base)]

        return sorted(path.relative_to(self._root).as_posix() for path in found)

    @override
    def local ( self, path: str ) -> Path:

        return self.resolve(path)
