from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import override

from core.error import Code, Fault
from core.fs import Driver, fs
from core.net import Egress
from .upload import KILO, PATTERN, Content, Intake, Stored
import builtins

class Storage(Intake):

    def __init__ ( self ) -> None:

        self._disks: dict[str, Driver] = {}
        self._default = "public"
        self._pattern = PATTERN
        self._limit   = 10 * KILO * KILO
        self._allowed: tuple[str, ...] = ()
        self._blocked: tuple[str, ...] = ()
        self._egress  = Egress()

    def setup (
        self, disks: Mapping[str, Driver], default: str = "public", pattern: str = PATTERN,
        limit: int = 10 * KILO * KILO, allowed: Sequence[str] = (), blocked: Sequence[str] = (),
        egress: Egress | None = None,
    ) -> None:

        self._disks   = dict(disks)
        self._default = default
        self._pattern = pattern
        self._limit   = limit
        self._allowed = tuple(allowed)
        self._blocked = tuple(item.lower().lstrip(".") for item in blocked)
        self._egress  = egress or Egress()

        for name, disk in self._disks.items(): fs.drivers.register(f"storage.{name}", disk)

    def register ( self, name: str, disk: Driver ) -> None:

        self._disks[name] = disk

        fs.drivers.register(f"storage.{name}", disk)

    def names ( self ) -> builtins.list[str]:

        return sorted(self._disks)

    def ready ( self ) -> bool:

        return self._default in self._disks

    def disk ( self, name: str | None = None ) -> Driver:

        return self._disks[self.label(name)]

    def label ( self, name: str | None = None ) -> str:

        chosen = name or self._default

        if chosen not in self._disks: raise Fault(Code.INTERNAL, reason=f"storage.{chosen}.missing")

        return chosen

    @override
    async def put ( self, path: str, data: Content, disk: str | None = None, mime: str | None = None ) -> Stored:

        label  = self.label(disk)
        target = self._disks[label]
        key    = self.clean(path)
        raw    = data.encode() if isinstance(data, str) else data
        kind   = self.mime(key, mime)
        size   = await target.put(key, raw, kind)

        return Stored(label, key, size, kind, target.url(key) if target.public() else None, Path(key).name)

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

    async def files ( self, prefix: str = "", disk: str | None = None ) -> builtins.list[str]:

        root  = f"{self.clean(prefix)}/" if prefix else ""
        found = await self.list(prefix, disk)

        return [path for path in found if "/" not in path.removeprefix(root)]

    async def directories ( self, prefix: str = "", disk: str | None = None ) -> builtins.list[str]:

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

    async def list ( self, prefix: str = "", disk: str | None = None ) -> builtins.list[str]:

        return await self.disk(disk).list(self.clean(prefix) if prefix else "")

    def url ( self, path: str, disk: str | None = None ) -> str:

        return self.disk(disk).url(self.clean(path))

    async def temporary_url ( self, path: str, seconds: int = 900, disk: str | None = None ) -> str:

        return await self.disk(disk).temporary_url(self.clean(path), seconds)

    def local ( self, path: str, disk: str | None = None ) -> Path:

        return self.disk(disk).local(self.clean(path))

    def describe ( self ) -> dict[str, object]:

        return {
            "default": self._default, "disks": { name: disk.describe() for name, disk in sorted(self._disks.items()) },
            "pattern": self._pattern, "limit": self._limit, "allowed": list(self._allowed),
            "blocked": list(self._blocked),
        }
