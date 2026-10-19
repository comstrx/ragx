from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from core.error import Code, Fault
from core.json import json
from core.thread import Deadline, Process, thread
import filetype, os, stat, sys

@dataclass(frozen=True, slots=True)
class ExtractPolicy:

    max_bytes : int = 16 * 1024 * 1024
    max_chars : int = 500_000
    max_pages : int = 100
    seconds   : float = 20.0
    root      : str | None = None

    def __post_init__ ( self ) -> None:

        if min(self.max_bytes, self.max_chars, self.max_pages, self.seconds) <= 0:
            raise Fault(Code.VALIDATION, reason="file.limits")

@dataclass(frozen=True, slots=True)
class Part:

    text   : str
    page   : int | None = None
    second : float | None = None

@dataclass(frozen=True, slots=True)
class Extracted:

    source : str
    mime   : str
    parts  : tuple[Part, ...]

    @property
    def text ( self ) -> str:

        return "\n\n".join(part.text for part in self.parts)

type Converter = Callable[[bytes, str, str], Awaitable[tuple[Part, ...]]]

class Extraction:

    def read ( self, path: str | Path, policy: ExtractPolicy ) -> tuple[str, bytes, str]:

        target = Path(path).expanduser()
        try: descriptor = self.descriptor(target, policy.root)
        except OSError as error: raise Fault(Code.FORBIDDEN, reason="file.path") from error

        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise Fault(Code.FORBIDDEN, reason="file.regular")
            data = stream.read(policy.max_bytes + 1)
        if len(data) > policy.max_bytes: raise Fault(Code.VALIDATION, reason="file.size")

        if data.startswith((b"MZ", b"\x7fELF")): raise Fault(Code.VALIDATION, reason="file.type")
        kind = filetype.guess(data[:8192])
        mime = str(kind.mime) if kind is not None else "text/plain"
        if kind is None:
            if b"\x00" in data or data.startswith((b"MZ", b"\x7fELF")):
                raise Fault(Code.VALIDATION, reason="file.type")
            try: data.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error: raise Fault(Code.VALIDATION, reason="file.encoding") from error

        return target.name, data, mime

    def descriptor ( self, target: Path, allowed: str | None ) -> int:

        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if allowed is None: return os.open(target, flags)
        root = Path(allowed).expanduser().resolve()
        try: parts = target.absolute().relative_to(root).parts
        except ValueError as error: raise Fault(Code.FORBIDDEN, reason="file.root") from error
        if not parts or ".." in parts: raise Fault(Code.FORBIDDEN, reason="file.root")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for component in parts[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            return os.open(parts[-1], flags, dir_fd=directory)
        finally: os.close(directory)

    async def convert (
        self, name: str, data: bytes, mime: str, policy: ExtractPolicy, converter: Converter | None,
    ) -> Extracted:

        if converter is None: raise Fault(Code.VALIDATION, reason="file.converter.unsupported")
        async with Deadline(policy.seconds, "file.conversion.timeout"):
            parts = await converter(data, mime, name)
        if sum(len(part.text) for part in parts) > policy.max_chars:
            raise Fault(Code.VALIDATION, reason="file.text.limit")
        if not any(part.text.strip() for part in parts): raise Fault(Code.VALIDATION, reason="file.conversion.empty")
        return Extracted(name, mime, parts)

    async def extract (
        self, path: str | Path, policy: ExtractPolicy | None = None, converter: Converter | None = None,
    ) -> Extracted:

        selected = policy or ExtractPolicy()
        name, data, mime = await thread.offload(self.read, path, selected)

        if mime == "text/plain":
            text = data.decode("utf-8")
            if len(text) > selected.max_chars: raise Fault(Code.VALIDATION, reason="file.text.limit")
            return Extracted(name, mime, (Part(text),))

        if mime == "application/pdf":
            process = await Process.start([
                sys.executable, "-m", "core.fs.extract_worker", str(selected.max_pages), str(selected.max_chars),
            ], log_limit=selected.max_chars * 6 + 65536, input_data=data, inherit=False)
            try:
                if await process.wait(selected.seconds) != 0: raise Fault(Code.VALIDATION, reason="file.pdf")
                parsed = json.loads(process.output())
                parts = tuple(Part(item["text"], item["page"]) for item in parsed)
            finally: await process.close()
            if any(part.text.strip() for part in parts): return Extracted(name, mime, parts)
            return await self.convert(name, data, mime, selected, converter)

        if not mime.startswith(("image/", "audio/", "video/")) or converter is None:
            raise Fault(Code.VALIDATION, reason="file.converter.unsupported")

        return await self.convert(name, data, mime, selected, converter)
