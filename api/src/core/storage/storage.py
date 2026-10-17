from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from core.date import date
from core.exceptions import Code, Fault
from core.rand import rand
from core.string import string
import mimetypes

type Content = bytes | str

PATTERN  = "{Y}/{m}/{d}"
FALLBACK = "application/octet-stream"
KILO     = 1024

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

class Disk(Protocol):

    @property
    def name ( self ) -> str: ...

    async def put ( self, path: str, data: bytes, mime: str ) -> int: ...

    async def get ( self, path: str ) -> bytes: ...

    async def stream ( self, path: str ) -> AsyncIterator[bytes]: ...

    async def exists ( self, path: str ) -> bool: ...

    async def size ( self, path: str ) -> int: ...

    async def delete ( self, path: str ) -> bool: ...

    async def copy ( self, source: str, target: str ) -> None: ...

    async def move ( self, source: str, target: str ) -> None: ...

    async def list ( self, prefix: str = "" ) -> list[str]: ...

    def url ( self, path: str ) -> str | None: ...

    async def temporary_url ( self, path: str, seconds: int ) -> str | None: ...

    def local ( self, path: str ) -> Path | None: ...

class Uploaded(Protocol):

    @property
    def filename ( self ) -> str | None: ...

    @property
    def content_type ( self ) -> str | None: ...

    @property
    def size ( self ) -> int | None: ...

    async def read ( self, size: int = -1 ) -> bytes: ...

class Storage:

    def __init__ ( self ) -> None:

        self._disks: dict[str, Disk] = {}
        self._default = "public"
        self._pattern = PATTERN
        self._limit   = 10 * KILO * KILO
        self._allowed: tuple[str, ...] = ()
        self._blocked: tuple[str, ...] = ()

    def setup (
        self, disks: Mapping[str, Disk], default: str = "public", pattern: str = PATTERN,
        limit: int = 10 * KILO * KILO, allowed: Sequence[str] = (), blocked: Sequence[str] = (),
    ) -> None:

        self._disks   = dict(disks)
        self._default = default
        self._pattern = pattern
        self._limit   = limit
        self._allowed = tuple(allowed)
        self._blocked = tuple(item.lower().lstrip(".") for item in blocked)

    def register ( self, name: str, disk: Disk ) -> None:
        self._disks[name] = disk

    def names ( self ) -> list[str]:
        return sorted(self._disks)

    def ready ( self ) -> bool:
        return self._default in self._disks

    def disk ( self, name: str | None = None ) -> Disk:

        found = self._disks.get(name or self._default)

        if found is None: raise Fault(Code.INTERNAL, reason=f"storage.{name or self._default}")

        return found

    def clean ( self, path: str ) -> str:

        parts = [part for part in PurePosixPath(path.replace("\\", "/")).parts if part not in ("", "/", ".")]

        if not parts or ".." in parts: raise Fault(Code.BAD_REQUEST, reason="storage.path")

        return "/".join(parts)

    def dated ( self, folder: str = "", pattern: str | None = None, moment: datetime | None = None ) -> str:

        now    = date.utc(moment or date.now())
        stamp  = (pattern or self._pattern).format(
            Y=f"{now.year:04d}", m=f"{now.month:02d}", d=f"{now.day:02d}", H=f"{now.hour:02d}", M=f"{now.minute:02d}",
            y=f"{now.year % 100:02d}", j=f"{now.timetuple().tm_yday:03d}", W=f"{now.isocalendar().week:02d}",
        )

        return self.clean(f"{folder}/{stamp}" if folder else stamp)

    def name ( self, original: str | None = None, keep: bool = False ) -> str:

        extension = self.extension(original)
        stem      = string.slug(Path(original or "").stem) if keep and original else str(rand.uuid())

        return f"{stem}.{extension}" if extension else stem

    def extension ( self, original: str | None ) -> str:
        return Path(original or "").suffix.lstrip(".").lower()

    def mime ( self, path: str, declared: str | None = None ) -> str:

        guessed, _ = mimetypes.guess_type(path)

        return (declared or guessed or FALLBACK).split(";")[0].strip().lower()

    async def put ( self, path: str, data: Content, disk: str | None = None, mime: str | None = None ) -> Stored:

        target = self.disk(disk)
        key    = self.clean(path)
        raw    = data.encode() if isinstance(data, str) else data
        kind   = self.mime(key, mime)
        size   = await target.put(key, raw, kind)

        return Stored(target.name, key, size, kind, target.url(key), Path(key).name)

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

        if self.extension(label) in self._blocked:

            refused = f"Files of type .{self.extension(label)} are not accepted"

            raise Fault(Code.VALIDATION, errors={ "file": [refused] })
        if len(data) == 0: raise Fault(Code.VALIDATION, errors={ "file": ["The file is empty"] })
        if len(data) > cap: raise Fault(Code.VALIDATION, errors={ "file": [f"The file exceeds {cap // KILO} KB"] })
        if kinds and not self.accepts(kind, kinds):
            raise Fault(Code.VALIDATION, errors={ "file": [f"Expected one of: {', '.join(kinds)}"] })

        place = self.clean(folder) if pattern == "" else self.dated(folder, pattern)

        return await self.put(f"{place}/{label}", data, disk, kind)

    def accepts ( self, kind: str, kinds: Sequence[str] ) -> bool:
        return any(kind == rule or (rule.endswith("/*") and kind.startswith(rule[:-1])) for rule in kinds)

    async def get ( self, path: str, disk: str | None = None ) -> bytes:
        return await self.disk(disk).get(self.clean(path))

    async def text ( self, path: str, disk: str | None = None ) -> str:
        return (await self.get(path, disk)).decode()

    async def stream ( self, path: str, disk: str | None = None ) -> AsyncIterator[bytes]:
        return await self.disk(disk).stream(self.clean(path))

    async def exists ( self, path: str, disk: str | None = None ) -> bool:
        return await self.disk(disk).exists(self.clean(path))

    async def size ( self, path: str, disk: str | None = None ) -> int:
        return await self.disk(disk).size(self.clean(path))

    async def delete ( self, path: str, disk: str | None = None ) -> bool:
        return await self.disk(disk).delete(self.clean(path))

    async def copy ( self, source: str, target: str, disk: str | None = None ) -> None:
        await self.disk(disk).copy(self.clean(source), self.clean(target))

    async def move ( self, source: str, target: str, disk: str | None = None ) -> None:
        await self.disk(disk).move(self.clean(source), self.clean(target))

    async def list ( self, prefix: str = "", disk: str | None = None ) -> list[str]:
        return await self.disk(disk).list(self.clean(prefix) if prefix else "")

    def url ( self, path: str, disk: str | None = None ) -> str | None:
        return self.disk(disk).url(self.clean(path))

    async def temporary_url ( self, path: str, seconds: int = 900, disk: str | None = None ) -> str | None:
        return await self.disk(disk).temporary_url(self.clean(path), seconds)

    def local ( self, path: str, disk: str | None = None ) -> Path | None:
        return self.disk(disk).local(self.clean(path))
