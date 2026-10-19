from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath, to_thread
from core.error import Code, Fault
from .path import Pathish
from .scan import Scan
import shutil, time

type Tree = dict[str, Any]

class Dir(Scan):

    async def exists ( self, target: Pathish ) -> bool:

        return await AsyncPath(target).is_dir()

    async def make ( self, target: Pathish ) -> Path:

        await AsyncPath(target).mkdir(parents=True, exist_ok=True)

        return Path(target)

    async def entries ( self, folder: Pathish, pattern: str = "*" ) -> list[Path]:

        if not await self.exists(folder): return []

        return sorted([Path(entry) async for entry in AsyncPath(folder).glob(pattern)])

    async def files ( self, folder: Pathish, pattern: str = "*", recursive: bool = False ) -> list[Path]:

        found = await self.entries(folder, f"**/{pattern}" if recursive else pattern)

        return [path for path in found if path.is_file()]

    async def dirs ( self, folder: Pathish, recursive: bool = False ) -> list[Path]:

        found = await self.entries(folder, "**/*" if recursive else "*")

        return [path for path in found if path.is_dir()]

    async def walk ( self, folder: Pathish, pattern: str = "**/*" ) -> AsyncIterator[Path]:

        async for entry in AsyncPath(folder).glob(pattern):
            if await entry.is_file(): yield Path(entry)

    async def tree ( self, folder: Pathish, depth: int = 3 ) -> Tree:

        root = Path(folder)

        if not await self.exists(root): raise Fault(Code.NOT_FOUND, reason="fs.missing")

        return await to_thread.run_sync(self.branch, root, depth)

    def branch ( self, path: Path, left: int ) -> Tree:

        node: Tree = { "name": path.name, "kind": "dir", "children": [] }

        if left <= 0: return node

        for child in sorted(path.iterdir()):

            if child.is_dir(): node["children"].append(self.branch(child, left - 1))
            else: node["children"].append({ "name": child.name, "kind": "file", "size": child.stat().st_size })

        return node

    async def size ( self, folder: Pathish ) -> int:

        total = 0

        async for path in self.walk(folder): total += path.stat().st_size

        return total

    async def count ( self, folder: Pathish, pattern: str = "**/*" ) -> int:

        found = 0

        async for _ in self.walk(folder, pattern): found += 1

        return found

    async def empty ( self, folder: Pathish ) -> bool:

        if not await self.exists(folder): return True

        async for _ in AsyncPath(folder).iterdir(): return False

        return True

    async def clear ( self, folder: Pathish ) -> int:

        removed = 0

        async for child in AsyncPath(folder).iterdir():

            if await child.is_dir(): await self.remove(Path(child))
            else: await child.unlink()

            removed += 1

        return removed

    async def remove ( self, target: Pathish ) -> bool:

        path = Path(target)

        if not await AsyncPath(path).is_dir(): return False

        await to_thread.run_sync(shutil.rmtree, str(path))

        return True

    async def copy ( self, source: Pathish, target: Pathish ) -> Path:

        if not await self.exists(source): raise Fault(Code.NOT_FOUND, reason="fs.missing")

        await to_thread.run_sync(lambda: shutil.copytree(str(source), str(target), dirs_exist_ok=True))

        return Path(target)

    async def move ( self, source: Pathish, target: Pathish ) -> Path:

        if not await self.exists(source): raise Fault(Code.NOT_FOUND, reason="fs.missing")

        await AsyncPath(Path(target).parent).mkdir(parents=True, exist_ok=True)
        await to_thread.run_sync(shutil.move, str(source), str(target))

        return Path(target)

    async def newest ( self, folder: Pathish, pattern: str = "*" ) -> Path | None:

        files = await self.files(folder, pattern)

        return max(files, key=lambda path: path.stat().st_mtime, default=None)

    async def oldest ( self, folder: Pathish, pattern: str = "*" ) -> Path | None:

        files = await self.files(folder, pattern)

        return min(files, key=lambda path: path.stat().st_mtime, default=None)

    async def largest ( self, folder: Pathish, pattern: str = "*" ) -> Path | None:

        files = await self.files(folder, pattern)

        return max(files, key=lambda path: path.stat().st_size, default=None)

    async def prune ( self, folder: Pathish, older_than: float, pattern: str = "*" ) -> int:

        edge    = time.time() - older_than
        removed = 0

        for path in await self.files(folder, pattern, recursive=True):

            if path.stat().st_mtime < edge:

                path.unlink()

                removed += 1

        return removed

    async def describe ( self, folder: Pathish ) -> dict[str, Any]:

        files = await self.files(folder, recursive=True)

        return { "path": str(folder), "files": len(files), "bytes": sum(path.stat().st_size for path in files) }
