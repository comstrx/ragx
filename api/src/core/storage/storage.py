from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime
from pathlib import Path

from core.date import date
from core.error import Code, Fault
from core.fs import fs
from core.net import Client, net
from core.rand import rand
from core.string import string
from .disk import Disk, Stored, Uploaded

type Content = bytes | str

PATTERN = "{Y}/{m}/{d}"
KILO    = 1024

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

        for name, disk in self._disks.items(): fs.drivers.register(f"storage.{name}", disk)

    def register ( self, name: str, disk: Disk ) -> None:

        self._disks[name] = disk

        fs.drivers.register(f"storage.{name}", disk)

    def names ( self ) -> list[str]:
        return sorted(self._disks)

    def ready ( self ) -> bool:
        return self._default in self._disks

    def disk ( self, name: str | None = None ) -> Disk:

        found = self._disks.get(name or self._default)

        if found is None: raise Fault(Code.INTERNAL, reason=f"storage.{name or self._default}")

        return found

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

    async def get ( self, path: str, disk: str | None = None ) -> bytes:
        return await self.disk(disk).get(self.clean(path))

    async def text ( self, path: str, disk: str | None = None ) -> str:
        return (await self.get(path, disk)).decode()

    async def stream ( self, path: str, disk: str | None = None ) -> AsyncIterator[bytes]:
        return await self.disk(disk).stream(self.clean(path))

    async def exists ( self, path: str, disk: str | None = None ) -> bool:
        return await self.disk(disk).exists(self.clean(path))

    async def missing ( self, path: str, disk: str | None = None ) -> bool:
        return not await self.exists(path, disk)

    async def last_modified ( self, path: str, disk: str | None = None ) -> float:
        return await self.disk(disk).modified(self.clean(path))

    async def append ( self, path: str, data: Content, disk: str | None = None ) -> Stored:

        raw   = data.encode() if isinstance(data, str) else data
        known = await self.get(path, disk) if await self.exists(path, disk) else b""

        return await self.put(path, known + raw, disk)

    async def prepend ( self, path: str, data: Content, disk: str | None = None ) -> Stored:

        raw   = data.encode() if isinstance(data, str) else data
        known = await self.get(path, disk) if await self.exists(path, disk) else b""

        return await self.put(path, raw + known, disk)

    async def files ( self, prefix: str = "", disk: str | None = None ) -> list[str]:

        root  = f"{self.clean(prefix)}/" if prefix else ""
        found = await self.list(prefix, disk)

        return [path for path in found if "/" not in path.removeprefix(root)]

    async def directories ( self, prefix: str = "", disk: str | None = None ) -> list[str]:

        root  = f"{self.clean(prefix)}/" if prefix else ""
        found = await self.list(prefix, disk)
        heads = { path.removeprefix(root).split("/", 1)[0] for path in found if "/" in path.removeprefix(root) }

        return sorted(f"{root}{name}" for name in heads)

    async def delete_directory ( self, prefix: str, disk: str | None = None ) -> int:

        target  = self.disk(disk)
        removed = 0

        for path in await target.list(self.clean(prefix)):
            if await target.delete(path): removed += 1

        return removed

    async def size ( self, path: str, disk: str | None = None ) -> int:
        return await self.disk(disk).size(self.clean(path))

    async def delete ( self, path: str, disk: str | None = None ) -> bool:
        return await self.disk(disk).delete(self.clean(path))

    async def copy ( self, source: str, target: str, disk: str | None = None ) -> None:
        await self.disk(disk).copy(self.clean(source), self.clean(target))

    async def move ( self, source: str, target: str, disk: str | None = None ) -> None:
        await self.disk(disk).move(self.clean(source), self.clean(target))

    async def transfer ( self, path: str, source: str, target: str ) -> Stored:

        data = await self.get(path, source)

        return await self.put(path, data, target)

    async def list ( self, prefix: str = "", disk: str | None = None ) -> list[str]:
        return await self.disk(disk).list(self.clean(prefix) if prefix else "")

    def url ( self, path: str, disk: str | None = None ) -> str | None:
        return self.disk(disk).url(self.clean(path))

    async def temporary_url ( self, path: str, seconds: int = 900, disk: str | None = None ) -> str | None:
        return await self.disk(disk).temporary_url(self.clean(path), seconds)

    def local ( self, path: str, disk: str | None = None ) -> Path | None:
        return self.disk(disk).local(self.clean(path))

    def describe ( self ) -> dict[str, object]:

        return {
            "default": self._default, "disks": self.names(), "pattern": self._pattern, "limit": self._limit,
            "allowed": list(self._allowed), "blocked": list(self._blocked),
        }
