from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from .archive import Archive
from .base import Pathish
from .dir import Dir
from .editor import Editor
from .driver import Driver
from .drivers import Drivers
from .file import File
from .path import Paths
from .watch import Watch

class Fs(Paths):

    def __init__ ( self ) -> None:

        self.file    = File()
        self.dir     = Dir()
        self.drivers = Drivers()
        self.archive = Archive()
        self.editor  = Editor()

    def watch ( self, target: Pathish, every: float = 0.5, recursive: bool = True ) -> Watch:

        return Watch(target, every, recursive)

    def driver ( self, name: str ) -> Driver:

        return self.drivers.use(name)

    def use ( self, name: str ) -> Driver:

        return self.drivers.use(name)

    async def exists ( self, target: Pathish ) -> bool:

        return await self.file.exists(target) or await self.dir.exists(target)

    async def is_file ( self, target: Pathish ) -> bool:

        return await self.file.exists(target)

    async def is_dir ( self, target: Pathish ) -> bool:

        return await self.dir.exists(target)

    async def size ( self, target: Pathish ) -> int:

        return await self.dir.size(target) if await self.dir.exists(target) else await self.file.size(target)

    async def mkdir ( self, target: Pathish ) -> Path:

        return await self.dir.make(target)

    async def read_text ( self, target: Pathish, encoding: str = "utf-8" ) -> str:

        return await self.file.read_text(target, encoding)

    async def read_bytes ( self, target: Pathish ) -> bytes:

        return await self.file.read_bytes(target)

    async def read_json ( self, target: Pathish ) -> Any:

        return await self.file.read_json(target)

    async def write_text ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:

        return await self.file.write_text(target, text, encoding)

    async def write_bytes ( self, target: Pathish, data: bytes ) -> Path:

        return await self.file.write_bytes(target, data)

    async def write_json ( self, target: Pathish, value: object ) -> Path:

        return await self.file.write_json(target, value)

    async def append ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:

        return await self.file.append(target, text, encoding)

    async def remove ( self, target: Pathish ) -> bool:

        return await self.file.remove(target) or await self.dir.remove(target)

    async def copy ( self, source: Pathish, target: Pathish ) -> Path:

        if await self.dir.exists(source): return await self.dir.copy(source, target)

        return await self.file.copy(source, target)

    async def move ( self, source: Pathish, target: Pathish ) -> Path:

        if await self.dir.exists(source): return await self.dir.move(source, target)

        return await self.file.move(source, target)

    async def list ( self, folder: Pathish, pattern: str = "*" ) -> list[Path]:

        return await self.dir.entries(folder, pattern)

    async def walk ( self, folder: Pathish, pattern: str = "**/*" ) -> AsyncIterator[Path]:

        async for path in self.dir.walk(folder, pattern): yield path

    async def checksum ( self, target: Pathish, algorithm: str = "sha256" ) -> str:

        return await self.file.checksum(target, algorithm)

    def mime ( self, target: Pathish, declared: str | None = None ) -> str:

        return self.file.mime(target, declared)
