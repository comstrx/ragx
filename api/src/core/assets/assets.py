from pathlib import Path, PurePosixPath

from core.error import Code, Fault
from core.fs import fs
import builtins, hashlib, mimetypes

STAMP    = 10
FALLBACK = "application/octet-stream"

class Assets:

    def __init__ ( self ) -> None:

        self._folder: Path | None = None
        self._prefix    = "/assets"
        self._base      = ""
        self._versioned = True
        self._stamps: dict[str, str | None] = {}

    def setup ( self, folder: Path, prefix: str = "/assets", base: str = "", versioned: bool = True ) -> None:

        self._folder    = folder.resolve()
        self._prefix    = "/" + prefix.strip("/")
        self._base      = base.rstrip("/")
        self._versioned = versioned
        self._stamps    = {}

    def ready ( self ) -> bool:

        return self._folder is not None

    def folder ( self ) -> Path:

        if self._folder is None: raise Fault(Code.INTERNAL, reason="assets")

        return self._folder

    def prefix ( self ) -> str:

        return self._prefix

    def clean ( self, path: str ) -> str:

        parts = [part for part in PurePosixPath(path.replace("\\", "/")).parts if part not in ("", "/", ".")]

        if not parts or any(part == ".." or part.startswith(".") for part in parts):
            raise Fault(Code.BAD_REQUEST, reason="assets.path")

        return "/".join(parts)

    def path ( self, path: str ) -> Path:

        target = (self.folder() / self.clean(path)).resolve()

        if not fs.within(self.folder(), target): raise Fault(Code.BAD_REQUEST, reason="assets.path")

        return target

    def exists ( self, path: str ) -> bool:

        return self.path(path).is_file()

    def stamp ( self, path: str ) -> str | None:

        key = self.clean(path)

        if key not in self._stamps:

            target = self.path(key)

            self._stamps[key] = hashlib.sha256(target.read_bytes()).hexdigest()[:STAMP] if target.is_file() else None

        return self._stamps[key]

    def url ( self, path: str, absolute: bool | None = None ) -> str:

        key   = self.clean(path)
        stamp = self.stamp(key) if self._versioned else None
        href  = f"{self._prefix}/{key}{f'?v={stamp}' if stamp else ''}"
        full  = absolute if absolute is not None else bool(self._base)

        return f"{self._base}{href}" if full and self._base else href

    def mime ( self, path: str ) -> str:

        guessed, _ = mimetypes.guess_type(self.clean(path))

        return guessed or FALLBACK

    async def read ( self, path: str ) -> bytes:

        target = self.path(path)

        if not target.is_file(): raise Fault(Code.NOT_FOUND, reason="assets.missing")

        return await fs.read_bytes(target)

    async def text ( self, path: str ) -> str:

        return (await self.read(path)).decode()

    async def list ( self, prefix: str = "" ) -> builtins.list[str]:

        base  = self.path(prefix) if prefix else self.folder()
        found = [entry async for entry in fs.walk(base) if entry.is_file() and not entry.name.startswith(".")]

        return sorted(entry.relative_to(self.folder()).as_posix() for entry in found)

    def forget ( self ) -> None:

        self._stamps.clear()
