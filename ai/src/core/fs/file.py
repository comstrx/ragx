from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath
from core.error import Code, Fault
from core.json import json
from .base import CHUNK, FALLBACK, Pathish
from .kind import Kind
from .atomic import atomic_bytes
import anyio, hashlib, mimetypes, os, stat as modes

HASHES = ("sha256", "sha512", "blake2b", "md5")

class File(Kind):

    async def exists ( self, target: Pathish ) -> bool:

        return await AsyncPath(target).is_file()

    async def size ( self, target: Pathish ) -> int:

        try: return (await AsyncPath(target).stat()).st_size
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def modified ( self, target: Pathish ) -> float:

        try: return (await AsyncPath(target).stat()).st_mtime
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def touch ( self, target: Pathish ) -> Path:

        path = AsyncPath(target)

        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.touch()

        return Path(target)

    async def read_text ( self, target: Pathish, encoding: str = "utf-8" ) -> str:

        try: return await AsyncPath(target).read_text(encoding=encoding)
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def read_bytes ( self, target: Pathish ) -> bytes:

        try: return await AsyncPath(target).read_bytes()
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

    async def read_json ( self, target: Pathish ) -> Any:

        return json.loads(await self.read_bytes(target))

    async def read_lines ( self, target: Pathish, encoding: str = "utf-8" ) -> list[str]:

        return (await self.read_text(target, encoding)).splitlines()

    async def head ( self, target: Pathish, count: int = 10 ) -> list[str]:

        return (await self.read_lines(target))[:count]

    async def tail ( self, target: Pathish, count: int = 10 ) -> list[str]:

        lines = await self.read_lines(target)

        return lines[-count:] if count else []

    async def write_text ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:

        return await self.write_bytes(target, text.encode(encoding))

    async def write_json ( self, target: Pathish, value: object ) -> Path:

        return await self.write_bytes(target, json.encode(value, pretty=True))

    async def write_lines ( self, target: Pathish, lines: Iterable[str], encoding: str = "utf-8" ) -> Path:

        return await self.write_text(target, "\n".join(lines) + "\n", encoding)

    async def write_bytes ( self, target: Pathish, data: bytes ) -> Path:

        return await anyio.to_thread.run_sync(atomic_bytes, Path(target), data)

    async def write_stream ( self, target: Pathish, chunks: AsyncIterator[bytes] ) -> int:

        path  = Path(target)
        temp  = path.with_name(f".{path.name}.{os.getpid()}.part")
        total = 0

        await AsyncPath(path.parent).mkdir(parents=True, exist_ok=True)

        async with await anyio.open_file(temp, "wb") as handle:

            async for chunk in chunks:

                await handle.write(chunk)

                total += len(chunk)

        await AsyncPath(temp).replace(path)

        return total

    async def append ( self, target: Pathish, text: str, encoding: str = "utf-8" ) -> Path:

        await AsyncPath(Path(target).parent).mkdir(parents=True, exist_ok=True)

        async with await anyio.open_file(target, "a", encoding=encoding) as handle: await handle.write(text)

        return Path(target)

    async def chunks ( self, target: Pathish, size: int = CHUNK ) -> AsyncIterator[bytes]:

        if not await self.exists(target): raise Fault(Code.NOT_FOUND, reason=str(target))

        async with await anyio.open_file(target, "rb") as handle:

            while chunk := await handle.read(size): yield chunk

    async def remove ( self, target: Pathish ) -> bool:

        path = AsyncPath(target)

        if not await path.is_file(): return False

        await path.unlink()

        return True

    async def copy ( self, source: Pathish, target: Pathish ) -> Path:

        await self.write_stream(target, self.chunks(source))

        return Path(target)

    async def move ( self, source: Pathish, target: Pathish ) -> Path:

        await AsyncPath(Path(target).parent).mkdir(parents=True, exist_ok=True)

        try: await AsyncPath(source).rename(target)
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(source)) from error
        except OSError:

            await self.copy(source, target)
            await self.remove(source)

        return Path(target)

    async def rename ( self, source: Pathish, name: str ) -> Path:

        return await self.move(source, Path(source).with_name(name))

    async def checksum ( self, target: Pathish, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise Fault(Code.INTERNAL, reason=f"fs.algorithm.{algorithm}")

        digest = hashlib.new(algorithm)

        async for chunk in self.chunks(target): digest.update(chunk)

        return digest.hexdigest()

    async def same ( self, left: Pathish, right: Pathish ) -> bool:

        return await self.checksum(left) == await self.checksum(right)

    def mime ( self, target: Pathish, declared: str | None = None ) -> str:

        guessed, _ = mimetypes.guess_type(str(target))

        return (declared or guessed or FALLBACK).split(";")[0].strip().lower()

    async def replace ( self, target: Pathish, old: str, new: str ) -> int:

        text  = await self.read_text(target)
        count = text.count(old)

        if count: await self.write_text(target, text.replace(old, new))

        return count

    async def backup ( self, target: Pathish, suffix: str = ".bak" ) -> Path:

        source = Path(target)
        copy   = source.with_name(f"{source.name}{suffix}")

        return await self.copy(source, copy)

    async def chmod ( self, target: Pathish, mode: int ) -> Path:

        await AsyncPath(target).chmod(mode)

        return Path(target)

    async def times ( self, target: Pathish ) -> dict[str, float]:

        try: found = await AsyncPath(target).stat()
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

        return { "created": found.st_ctime, "modified": found.st_mtime, "accessed": found.st_atime }

    async def is_runnable ( self, target: Pathish ) -> bool:

        try: found = await AsyncPath(target).stat()
        except FileNotFoundError: return False

        return bool(found.st_mode & modes.S_IXUSR)

    async def describe ( self, target: Pathish ) -> dict[str, Any]:

        try: stat = await AsyncPath(target).stat()
        except FileNotFoundError as error: raise Fault(Code.NOT_FOUND, reason=str(target)) from error

        return {
            "path": str(target), "size": stat.st_size, "modified": stat.st_mtime, "created": stat.st_ctime,
            "mime": self.mime(target), "extension": Path(target).suffix.lstrip(".").lower(),
        }
