from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.fs import Driver, LocalDriver, S3Driver, S3Options

@dataclass(frozen=True, slots=True)
class Stored:

    disk : str
    path : str
    size : int
    mime : str
    url  : str | None = None
    name : str | None = None

    def dump ( self ) -> dict[str, object]:

        return {
            "disk": self.disk, "path": self.path, "size": self.size, "mime": self.mime, "url": self.url,
            "name": self.name,
        }

class Disk(Driver, Protocol):

    @property
    def name ( self ) -> str: ...

class Uploaded(Protocol):

    @property
    def filename ( self ) -> str | None: ...

    @property
    def content_type ( self ) -> str | None: ...

    @property
    def size ( self ) -> int | None: ...

    async def read ( self, size: int = -1 ) -> bytes: ...

class LocalDisk(LocalDriver):

    def __init__ ( self, name: str, root: Path, url: str | None = None ) -> None:

        super().__init__(root, url)

        self._name = name

    @property
    def name ( self ) -> str:
        return self._name

class S3Disk(S3Driver):

    def __init__ ( self, name: str, bucket: str, options: S3Options | None = None, url: str | None = None ) -> None:

        super().__init__(bucket, options, url)

        self._name = name

    @property
    def name ( self ) -> str:
        return self._name
