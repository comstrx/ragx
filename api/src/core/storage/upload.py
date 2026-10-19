from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from core.date import date
from core.error import Code, Fault
from core.fs import fs
from core.net import Client, net
from core.rand import rand
from core.string import string

type Content = bytes | str

PATTERN = "{Y}/{m}/{d}"
KILO    = 1024

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

class Uploaded(Protocol):

    @property
    def filename ( self ) -> str | None: ...

    @property
    def content_type ( self ) -> str | None: ...

    @property
    def size ( self ) -> int | None: ...

    async def read ( self, size: int = -1 ) -> bytes: ...

class Intake(ABC):

    _pattern : str
    _limit   : int
    _allowed : tuple[str, ...]
    _blocked : tuple[str, ...]

    @abstractmethod
    async def put ( self, path: str, data: Content, disk: str | None = None, mime: str | None = None ) -> Stored: ...

    def clean ( self, path: str ) -> str:

        parts = fs.segments(path)

        if not parts or ".." in parts: raise Fault(Code.BAD_REQUEST, reason="storage.path")

        return "/".join(parts)

    def dated ( self, folder: str = "", pattern: str | None = None, moment: datetime | None = None ) -> str:

        now   = date.utc(moment or date.now())
        stamp = (pattern or self._pattern).format(
            Y=f"{now.year:04d}", m=f"{now.month:02d}", d=f"{now.day:02d}", H=f"{now.hour:02d}", M=f"{now.minute:02d}",
            y=f"{now.year % 100:02d}", j=f"{now.timetuple().tm_yday:03d}", W=f"{now.isocalendar().week:02d}",
        )

        return self.clean(f"{folder}/{stamp}" if folder else stamp)

    def name ( self, original: str | None = None, keep: bool = False ) -> str:

        extension = self.extension(original)
        stem      = string.slug(Path(original or "").stem) if keep and original else str(rand.uuid())

        return f"{stem}.{extension}" if extension else stem

    def extension ( self, original: str | None ) -> str:

        return fs.extension(original or "")

    def mime ( self, path: str, declared: str | None = None ) -> str:

        return fs.mime(path, declared)

    async def put_dated (
        self, folder: str, name: str, data: Content, disk: str | None = None, pattern: str | None = None,
        mime: str | None = None,
    ) -> Stored:

        return await self.put(f"{self.dated(folder, pattern)}/{name}", data, disk, mime)

    async def upload (
        self, file: Uploaded, folder: str = "uploads", *, disk: str | None = None, allowed: Sequence[str] = (),
        limit: int | None = None, keep: bool = False, pattern: str | None = None, name: str | None = None,
    ) -> Stored:

        data  = await file.read()
        label = name or self.name(file.filename, keep)
        kind  = self.mime(label, file.content_type)
        kinds = tuple(allowed) or self._allowed
        cap   = limit or self._limit

        self.refuse(label, data, kind, kinds, cap)

        place = self.clean(folder) if pattern == "" else self.dated(folder, pattern)

        return await self.put(f"{place}/{label}", data, disk, kind)

    async def fetch (
        self, url: str, folder: str = "downloads", *, disk: str | None = None, name: str | None = None,
        keep: bool = False, limit: int | None = None, client: Client | None = None, pattern: str | None = None,
    ) -> Stored:

        source = client or net
        cap    = limit or self._limit
        parts: list[bytes] = []
        total  = 0

        async for chunk in source.stream("GET", url):

            total += len(chunk)

            if total > cap: raise Fault(Code.VALIDATION, errors={ "file": [f"The file exceeds {cap // KILO} KB"] })

            parts.append(chunk)

        original = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        label    = name or self.name(original, keep)
        place    = self.clean(folder) if pattern == "" else self.dated(folder, pattern)

        return await self.put(f"{place}/{label}", b"".join(parts), disk, self.mime(label))

    def refuse ( self, label: str, data: bytes, kind: str, kinds: Sequence[str], cap: int ) -> None:

        extension = self.extension(label)

        if extension in self._blocked:
            raise Fault(Code.VALIDATION, errors={ "file": [f"Files of type .{extension} are not accepted"] })
        if len(data) == 0: raise Fault(Code.VALIDATION, errors={ "file": ["The file is empty"] })
        if len(data) > cap: raise Fault(Code.VALIDATION, errors={ "file": [f"The file exceeds {cap // KILO} KB"] })
        if kinds and not self.accepts(kind, kinds):
            raise Fault(Code.VALIDATION, errors={ "file": [f"Expected one of: {', '.join(kinds)}"] })

    def accepts ( self, kind: str, kinds: Sequence[str] ) -> bool:

        return any(kind == rule or (rule.endswith("/*") and kind.startswith(rule[:-1])) for rule in kinds)
