from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, ClassVar, override

from core.adapter import Adapter
from .file import File
from .path import Pathish
import builtins

FILES  = "files"
STREAM = "stream"
LIST   = "list"
PATH   = "path"
SIGN   = "sign"
CORE   = frozenset({FILES, STREAM, LIST})

class Driver(Adapter, ABC):

    family       : ClassVar[str] = "fs"
    capabilities : ClassVar[frozenset[str]] = CORE

    def __init__ ( self, url: str | None = None ) -> None:

        self._url = url.rstrip("/") if url else None

    @abstractmethod
    async def put ( self, path: str, data: bytes, mime: str ) -> int: ...

    @abstractmethod
    async def get ( self, path: str ) -> bytes: ...

    @abstractmethod
    async def stream ( self, path: str ) -> AsyncIterator[bytes]: ...

    @abstractmethod
    async def exists ( self, path: str ) -> bool: ...

    @abstractmethod
    async def size ( self, path: str ) -> int: ...

    @abstractmethod
    async def modified ( self, path: str ) -> float: ...

    @abstractmethod
    async def delete ( self, path: str ) -> bool: ...

    @abstractmethod
    async def copy ( self, source: str, target: str ) -> None: ...

    @abstractmethod
    async def move ( self, source: str, target: str ) -> None: ...

    @abstractmethod
    async def list ( self, prefix: str = "" ) -> builtins.list[str]: ...

    def public ( self ) -> bool:

        return self._url is not None

    def url ( self, path: str ) -> str:

        self.missing(("url", self._url))

        return f"{self._url}/{path}"

    async def temporary_url ( self, path: str, seconds: int ) -> str:

        raise self.unsupported(SIGN)

    def local ( self, path: str ) -> Path:

        raise self.unsupported(PATH)

    async def upload ( self, source: Pathish, path: str, mime: str | None = None ) -> int:

        return await transfer.upload(self, source, path, mime)

    async def download ( self, path: str, target: Pathish ) -> int:

        return await transfer.download(self, path, target)

    async def sync ( self, other: Driver, prefix: str = "" ) -> int:

        return await transfer.sync(self, other, prefix)

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "public": self.public() }

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
