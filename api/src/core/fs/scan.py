from collections.abc import Callable
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath, to_thread
from .base import Pathish
from .kind import Kind
import shutil

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

        found = [Path(path) async for path in AsyncPath(folder).rglob("*") if await self.bare(path)]

        return sorted(found)

    async def bare ( self, path: AsyncPath ) -> bool:
        return await path.is_dir() and not [child async for child in path.iterdir()]

    async def empty_files ( self, folder: Pathish ) -> list[Path]:

        found = [Path(path) async for path in AsyncPath(folder).rglob("*") if await self.hollow(path)]

        return sorted(found)

    async def hollow ( self, path: AsyncPath ) -> bool:
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
