from collections.abc import Callable
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath, to_thread
from .path import Pathish
import mimetypes, shutil

ARCHIVES    = frozenset({"zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar", "zst"})
DOCUMENTS   = frozenset({
    "pdf", "doc", "docx", "odt", "rtf", "xls", "xlsx", "ods", "csv", "ppt", "pptx", "odp", "epub",
})
EXECUTABLES = frozenset({"exe", "dll", "so", "dylib", "bin", "msi", "bat", "cmd", "sh", "bash", "com", "app", "jar"})
CODE        = frozenset({
    "py", "js", "ts", "tsx", "jsx", "rs", "go", "rb", "php", "java", "c", "h", "cpp", "cs", "swift",
})
KINDS       = ("image", "audio", "video", "archive", "document", "text", "code", "executable", "font", "other")

class Kind:

    def kind ( self, target: Pathish, declared: str | None = None ) -> str:

        extension = Path(target).suffix.lstrip(".").lower()
        guessed   = (declared or mimetypes.guess_type(str(target))[0] or "").split(";")[0].strip().lower()
        family    = guessed.split("/")[0]

        if extension in ARCHIVES: return "archive"
        if extension in EXECUTABLES: return "executable"
        if extension in CODE: return "code"
        if extension in DOCUMENTS: return "document"
        if family in ("image", "audio", "video", "font"): return family
        if family == "text" or guessed in ("application/json", "application/xml", "application/x-yaml"): return "text"

        return "other"

    def is_image ( self, target: Pathish ) -> bool:

        return self.kind(target) == "image"

    def is_audio ( self, target: Pathish ) -> bool:

        return self.kind(target) == "audio"

    def is_video ( self, target: Pathish ) -> bool:

        return self.kind(target) == "video"

    def is_archive ( self, target: Pathish ) -> bool:

        return self.kind(target) == "archive"

    def is_document ( self, target: Pathish ) -> bool:

        return self.kind(target) == "document"

    def is_text ( self, target: Pathish ) -> bool:

        return self.kind(target) in ("text", "code")

    def is_code ( self, target: Pathish ) -> bool:

        return self.kind(target) == "code"

    def is_executable ( self, target: Pathish ) -> bool:

        return self.kind(target) == "executable"

    def is_media ( self, target: Pathish ) -> bool:

        return self.kind(target) in ("image", "audio", "video")

    def kinds ( self ) -> tuple[str, ...]:

        return KINDS

kinds = Kind()

class Scan:

    async def disk_usage ( self, folder: Pathish ) -> dict[str, int]:

        usage = await to_thread.run_sync(shutil.disk_usage, str(folder))

        return { "total": usage.total, "used": usage.used, "free": usage.free }

    async def depth ( self, folder: Pathish ) -> int:

        root    = Path(folder)
        deepest = 0

        async for path in AsyncPath(root).rglob("*"):
            deepest = max(deepest, len(Path(path).relative_to(root).parts))

        return deepest

    async def categorize ( self, folder: Pathish, recursive: bool = True ) -> dict[str, list[Path]]:

        groups: dict[str, list[Path]] = { name: [] for name in kinds.kinds() }

        async for path in AsyncPath(folder).glob("**/*" if recursive else "*"):

            if await path.is_file(): groups[kinds.kind(Path(path))].append(Path(path))

        return { name: sorted(paths) for name, paths in groups.items() if paths }

    async def of_kind ( self, folder: Pathish, kind: str, recursive: bool = True ) -> list[Path]:

        return (await self.categorize(folder, recursive)).get(kind, [])

    async def images ( self, folder: Pathish, recursive: bool = True ) -> list[Path]:

        return await self.of_kind(folder, "image", recursive)

    async def videos ( self, folder: Pathish, recursive: bool = True ) -> list[Path]:

        return await self.of_kind(folder, "video", recursive)

    async def audios ( self, folder: Pathish, recursive: bool = True ) -> list[Path]:

        return await self.of_kind(folder, "audio", recursive)

    async def documents ( self, folder: Pathish, recursive: bool = True ) -> list[Path]:

        return await self.of_kind(folder, "document", recursive)

    async def archives ( self, folder: Pathish, recursive: bool = True ) -> list[Path]:

        return await self.of_kind(folder, "archive", recursive)

    async def empty_dirs ( self, folder: Pathish ) -> list[Path]:

        found = [Path(path) async for path in AsyncPath(folder).rglob("*") if await self._bare_(path)]

        return sorted(found)

    async def _bare_ ( self, path: AsyncPath ) -> bool:

        return await path.is_dir() and not [child async for child in path.iterdir()]

    async def empty_files ( self, folder: Pathish ) -> list[Path]:

        found = [Path(path) async for path in AsyncPath(folder).rglob("*") if await self._hollow_(path)]

        return sorted(found)

    async def _hollow_ ( self, path: AsyncPath ) -> bool:

        return await path.is_file() and (await path.stat()).st_size == 0

    async def search (
        self, folder: Pathish, needle: str, pattern: str = "**/*", names_only: bool = True,
    ) -> list[Path]:

        wanted = needle.lower()
        found: list[Path] = []

        async for path in AsyncPath(folder).glob(pattern):

            if wanted in path.name.lower(): found.append(Path(path))
            elif not names_only and await path.is_file() and kinds.is_text(Path(path)):

                try: text = await path.read_text(errors="replace")
                except OSError: continue

                if wanted in text.lower(): found.append(Path(path))

        return sorted(found)

    async def select ( self, folder: Pathish, test: Callable[[Path], bool], pattern: str = "**/*" ) -> list[Path]:

        return sorted([Path(path) async for path in AsyncPath(folder).glob(pattern) if test(Path(path))])

    async def summary ( self, folder: Pathish ) -> dict[str, Any]:

        grouped = await self.categorize(folder)

        return {
            "kinds": { name: len(paths) for name, paths in grouped.items() },
            "files": sum(len(paths) for paths in grouped.values()),
            "empty_dirs": len(await self.empty_dirs(folder)),
            "depth": await self.depth(folder),
        }
