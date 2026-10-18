from collections.abc import Callable, Mapping
from pathlib import Path

from .base import Pathish
from .file import File

PAIR = 2

class Editor:

    def __init__ ( self ) -> None:

        self._file = File()

    async def lines ( self, target: Pathish ) -> list[str]:
        return await self._file.read_lines(target)

    async def save ( self, target: Pathish, lines: list[str] ) -> Path:
        return await self._file.write_text(target, "\n".join(lines) + ("\n" if lines else ""))

    async def replace_line ( self, target: Pathish, number: int, text: str ) -> Path:

        lines = await self.lines(target)

        if not 1 <= number <= len(lines): raise IndexError(number)

        lines[number - 1] = text

        return await self.save(target, lines)

    async def insert_line ( self, target: Pathish, number: int, text: str ) -> Path:

        lines = await self.lines(target)

        lines.insert(max(number - 1, 0), text)

        return await self.save(target, lines)

    async def delete_lines ( self, target: Pathish, test: Callable[[str], bool] ) -> int:

        lines = await self.lines(target)
        kept  = [line for line in lines if not test(line)]

        await self.save(target, kept)

        return len(lines) - len(kept)

    async def insert_after ( self, target: Pathish, marker: str, text: str ) -> bool:

        lines = await self.lines(target)
        index = next((position for position, line in enumerate(lines) if marker in line), None)

        if index is None: return False

        lines.insert(index + 1, text)

        await self.save(target, lines)

        return True

    async def insert_before ( self, target: Pathish, marker: str, text: str ) -> bool:

        lines = await self.lines(target)
        index = next((position for position, line in enumerate(lines) if marker in line), None)

        if index is None: return False

        lines.insert(index, text)

        await self.save(target, lines)

        return True

    async def replace_between ( self, target: Pathish, start: str, end: str, text: str ) -> bool:

        content = await self._file.read_text(target)
        head    = content.find(start)
        tail    = content.find(end, head + len(start)) if head >= 0 else -1

        if head < 0 or tail < 0: return False

        await self._file.write_text(target, content[:head + len(start)] + text + content[tail:])

        return True

    def extract_between ( self, text: str, start: str, end: str ) -> str | None:

        head = text.find(start)
        tail = text.find(end, head + len(start)) if head >= 0 else -1

        return text[head + len(start):tail] if head >= 0 and tail >= 0 else None

    async def map_lines ( self, target: Pathish, transform: Callable[[str], str] ) -> Path:
        return await self.save(target, [transform(line) for line in await self.lines(target)])

    async def ensure_line ( self, target: Pathish, text: str ) -> bool:

        lines = await self.lines(target) if await self._file.exists(target) else []

        if text in lines: return False

        lines.append(text)

        await self.save(target, lines)

        return True

    def env_to_dict ( self, text: str ) -> dict[str, str]:

        found: dict[str, str] = {}

        for raw in text.splitlines():

            line = raw.strip()

            if not line or line.startswith("#") or "=" not in line: continue

            key, _, value = line.partition("=")
            value         = value.strip()

            if len(value) >= PAIR and value[0] == value[-1] and value[0] in "\"'": value = value[1:-1]

            found[key.strip().removeprefix("export ").strip()] = value

        return found

    def dict_to_env ( self, values: Mapping[str, object] ) -> str:
        return "".join(f"{key}={self.env_quote(str(value))}\n" for key, value in values.items())

    def env_quote ( self, value: str ) -> str:

        if value and not any(char in value for char in " #'\"$\n"): return value

        return "'" + value.replace("'", "'\\''") + "'"

    async def env_get ( self, target: Pathish, key: str, default: str | None = None ) -> str | None:
        return self.env_to_dict(await self._file.read_text(target)).get(key, default)

    async def env_set ( self, target: Pathish, key: str, value: object ) -> Path:

        lines    = await self.lines(target) if await self._file.exists(target) else []
        replaced = False
        written  = f"{key}={self.env_quote(str(value))}"

        for index, line in enumerate(lines):

            if self.key_of(line) == key and not line.lstrip().startswith("#"):

                lines[index] = written
                replaced     = True

        if not replaced: lines.append(written)

        return await self.save(target, lines)

    def key_of ( self, line: str ) -> str:
        return line.split("=", 1)[0].strip().removeprefix("export ").strip()

    async def env_delete ( self, target: Pathish, key: str ) -> int:
        return await self.delete_lines(target, lambda line: self.key_of(line) == key)

    async def env_merge ( self, target: Pathish, values: Mapping[str, object] ) -> Path:

        for key, value in values.items(): await self.env_set(target, key, value)

        return Path(target)

    async def env_load ( self, target: Pathish ) -> dict[str, str]:
        return self.env_to_dict(await self._file.read_text(target))
