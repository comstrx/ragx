from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from engine.error import Code, Fault
from .archive import Archive
from .dir import Dir
from .driver import Driver, transfer
from .editor import Editor
from .file import File
from .local import LocalDriver
from .path import Pathish, Paths
from .s3 import S3Driver, S3Options
from .watch import Watch
import builtins

class Drivers:

    def __init__ ( self ) -> None:

        self._known: dict[str, Driver] = {}

    def register ( self, name: str, driver: Driver ) -> Driver:

        self._known[name] = driver

        return driver

    def use ( self, name: str ) -> Driver:

        found = self._known.get(name)

        if found is None: raise Fault(Code.INTERNAL, reason=f"fs.{name}.missing")

        return found

    def has ( self, name: str ) -> bool:

        return name in self._known

    def names ( self ) -> list[str]:

        return sorted(self._known)

    def forget ( self, name: str ) -> bool:

        return self._known.pop(name, None) is not None

    async def sync ( self, source: str, target: str, prefix: str = "" ) -> int:

        return await transfer.sync(self.use(source), self.use(target), prefix)

    def local ( self, name: str, root: Pathish, url: str | None = None ) -> LocalDriver:

        driver = LocalDriver(Path(root), url)

        self.register(name, driver)

        return driver

    def s3 ( self, name: str, bucket: str, options: S3Options | None = None, url: str | None = None ) -> S3Driver:

        driver = S3Driver(bucket, options, url)

        self.register(name, driver)

        return driver

    def describe ( self ) -> dict[str, list[str]]:

        return { "drivers": self.names() }

class Fs(Paths):

    def __init__ ( self ) -> None:

        self.file    = File()
        self.dir     = Dir()
        self.drivers = Drivers()
        self.archive = Archive()
        self.editor  = Editor()

    def watch ( self, target: Pathish, every: float = 0.5, recursive: bool = True ) -> Watch:

        return Watch(target, every, recursive)

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

    async def list ( self, folder: Pathish, pattern: str = "*" ) -> builtins.list[Path]:

        return await self.dir.entries(folder, pattern)

    async def walk ( self, folder: Pathish, pattern: str = "**/*" ) -> AsyncIterator[Path]:

        async for path in self.dir.walk(folder, pattern): yield path

    async def checksum ( self, target: Pathish, algorithm: str = "sha256" ) -> str:

        return await self.file.checksum(target, algorithm)

    def mime ( self, target: Pathish, declared: str | None = None ) -> str:

        return self.file.mime(target, declared)
