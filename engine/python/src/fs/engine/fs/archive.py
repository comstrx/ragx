from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anyio import to_thread
from engine.error import Code, Fault
from .path import Pathish
import tarfile, zipfile

TARS = (".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz")

@dataclass(frozen=True, slots=True)
class Bounds:

    members : int = 10_000
    size    : int = 1 << 30
    ratio   : float = 200.0

    def check ( self, sizes: Sequence[tuple[int, int]], packed: int ) -> None:

        unpacked = sum(size for size, _ in sizes)
        swollen  = any(size > self.ratio * max(compressed, 1) for size, compressed in sizes if compressed)

        if len(sizes) > self.members or unpacked > self.size or swollen or unpacked > self.ratio * max(packed, 1):
            raise Fault(Code.BAD_REQUEST, reason="archive.bomb")

def within ( root: Path, member: str ) -> Path:

    target = (root / member).resolve()

    if target != root.resolve() and root.resolve() not in target.parents:
        raise Fault(Code.BAD_REQUEST, reason="archive.member")

    return target

def gather ( sources: Sequence[Path] ) -> list[tuple[Path, str]]:

    found: list[tuple[Path, str]] = []

    for source in sources:

        if source.is_dir():

            inner = [path for path in sorted(source.rglob("*")) if path.is_file()]

            found.extend((path, str(path.relative_to(source.parent))) for path in inner)

        elif source.is_file(): found.append((source, source.name))
        else: raise Fault(Code.NOT_FOUND, reason="fs.missing")

    return found

class Archive:

    async def zip ( self, target: Pathish, *sources: Pathish, level: int = 6 ) -> Path:

        def pack () -> Path:

            Path(target).parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as bundle:
                for path, name in gather([Path(source) for source in sources]): bundle.write(path, name)

            return Path(target)

        return await to_thread.run_sync(pack)

    async def unzip ( self, archive: Pathish, folder: Pathish, limits: Bounds | None = None ) -> list[Path]:

        def unpack () -> list[Path]:

            root = Path(folder)

            with zipfile.ZipFile(archive) as bundle:

                entries = bundle.infolist()

                sizes   = [(item.file_size, item.compress_size) for item in entries]

                (limits or Bounds()).check(sizes, Path(archive).stat().st_size)

                members = [within(root, member) for member in bundle.namelist()]

                root.mkdir(parents=True, exist_ok=True)

                bundle.extractall(root)

            return [member for member in members if member.is_file()]

        try: return await to_thread.run_sync(unpack)
        except (zipfile.BadZipFile, FileNotFoundError) as error:
            raise Fault(Code.BAD_REQUEST, reason="archive") from error

    async def tar ( self, target: Pathish, *sources: Pathish, compression: str = "gz" ) -> Path:

        def pack () -> Path:

            Path(target).parent.mkdir(parents=True, exist_ok=True)

            mode: Any = f"w:{compression}" if compression else "w"

            with tarfile.open(target, mode) as bundle:
                for path, name in gather([Path(source) for source in sources]): bundle.add(path, name)

            return Path(target)

        return await to_thread.run_sync(pack)

    async def untar ( self, archive: Pathish, folder: Pathish, limits: Bounds | None = None ) -> list[Path]:

        def unpack () -> list[Path]:

            root = Path(folder)

            with tarfile.open(archive) as bundle:

                entries = bundle.getmembers()

                (limits or Bounds()).check([(item.size, 0) for item in entries], Path(archive).stat().st_size)

                members = [within(root, member.name) for member in entries]

                root.mkdir(parents=True, exist_ok=True)

                bundle.extractall(root, filter="data")

            return [member for member in members if member.is_file()]

        try: return await to_thread.run_sync(unpack)
        except (tarfile.TarError, FileNotFoundError) as error:
            raise Fault(Code.BAD_REQUEST, reason="archive") from error

    async def extract ( self, archive: Pathish, folder: Pathish, limits: Bounds | None = None ) -> list[Path]:

        name = str(archive).lower()

        if name.endswith(".zip"): return await self.unzip(archive, folder, limits)
        if name.endswith(TARS): return await self.untar(archive, folder, limits)

        raise Fault(Code.BAD_REQUEST, reason="archive.kind")

    async def compress ( self, target: Pathish, *sources: Pathish ) -> Path:

        name = str(target).lower()

        if name.endswith(".zip"): return await self.zip(target, *sources)
        if name.endswith(TARS): return await self.tar(target, *sources, compression=self.compression(name))

        raise Fault(Code.BAD_REQUEST, reason="archive.kind")

    def compression ( self, name: str ) -> str:

        if name.endswith((".tgz", ".tar.gz")): return "gz"
        if name.endswith(".tar.bz2"): return "bz2"
        if name.endswith(".tar.xz"): return "xz"

        return ""

    async def members ( self, archive: Pathish ) -> list[str]:

        def listing () -> list[str]:

            if str(archive).lower().endswith(".zip"):
                with zipfile.ZipFile(archive) as bundle: return sorted(bundle.namelist())

            with tarfile.open(archive) as bundle: return sorted(member.name for member in bundle.getmembers())

        try: return await to_thread.run_sync(listing)
        except (zipfile.BadZipFile, tarfile.TarError, FileNotFoundError) as error:
            raise Fault(Code.BAD_REQUEST, reason="archive") from error

    def is_archive ( self, target: Pathish ) -> bool:

        return str(target).lower().endswith((".zip", *TARS))
