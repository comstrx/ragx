from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath
from core.exceptions import Code, Fault
from core.json import json
import anyio, os

type Pathish = str | Path

class Fs:

    def path ( self, *parts: Pathish ) -> Path:
        return Path(*parts)

    def name ( self, target: Pathish ) -> str:
        return Path(target).name

    def stem ( self, target: Pathish ) -> str:
        return Path(target).stem

    def extension ( self, target: Pathish ) -> str:
        return Path(target).suffix.lstrip(".").lower()

    async def exists ( self, target: Pathish ) -> bool:
        return await AsyncPath(target).exists()

    async def is_file ( self, target: Pathish ) -> bool:
        return await AsyncPath(target).is_file()

    async def is_dir ( self, target: Pathish ) -> bool:
        return await AsyncPath(target).is_dir()

    async def size ( self, target: Pathish ) -> int:
        return (await AsyncPath(target).stat()).st_size

    async def mkdir ( self, target: Pathish ) -> Path:

        await AsyncPath(target).mkdir(parents=True, exist_ok=True)

        return Path(target)

    async def read_text ( self, target: Pathish, encoding: str = "utf-8" ) -> str:

        try: return await AsyncPath(target).read_text(encoding=encoding)
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def read_bytes ( self, target: Pathish ) -> bytes:

        try: return await AsyncPath(target).read_bytes()
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def read_json ( self, target: Pathish ) -> Any:

        return json.loads(await self.read_bytes(target))

    async def write_text ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:
        return await self.write_bytes(target, text.encode(encoding))

    async def write_json ( self, target: Pathish, value: object ) -> Path:
        return await self.write_bytes(target, json.encode(value, pretty=True))

    async def write_bytes ( self, target: Pathish, data: bytes ) -> Path:

        path = Path(target)
        temp = path.with_name(f".{path.name}.{os.getpid()}.part")

        await AsyncPath(path.parent).mkdir(parents=True, exist_ok=True)
        await AsyncPath(temp).write_bytes(data)
        await AsyncPath(temp).replace(path)

        return path

    async def append ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:

        async with await anyio.open_file(target, "a", encoding=encoding) as handle: await handle.write(text)

        return Path(target)

    async def remove ( self, target: Pathish ) -> bool:

        path = AsyncPath(target)

        if await path.is_dir():

            async for child in path.iterdir(): await self.remove(Path(child))

            await path.rmdir()

            return True

        if await path.exists():

            await path.unlink()

            return True

        return False

    async def copy ( self, source: Pathish, target: Pathish ) -> Path:
        return await self.write_bytes(target, await self.read_bytes(source))

    async def move ( self, source: Pathish, target: Pathish ) -> Path:

        await AsyncPath(Path(target).parent).mkdir(parents=True, exist_ok=True)
        await AsyncPath(source).rename(target)

        return Path(target)

    async def list ( self, folder: Pathish, pattern: str = "*" ) -> list[Path]:

        found = [Path(entry) async for entry in AsyncPath(folder).glob(pattern)]

        return sorted(found)

    async def walk ( self, folder: Pathish, pattern: str = "**/*" ) -> AsyncIterator[Path]:

        async for entry in AsyncPath(folder).glob(pattern):
            if await entry.is_file(): yield Path(entry)

    def within ( self, base: Pathish, target: Pathish ) -> bool:

        try: Path(target).resolve().relative_to(Path(base).resolve())
        except ValueError: return False

        return True

    def join_lines ( self, lines: Iterable[str] ) -> str:
        return "\n".join(lines) + "\n"
