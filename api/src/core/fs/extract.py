from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from core.error import Code, Fault
from core.json import json
from core.thread import thread
import os, stat, sys

type Converter = Callable[[bytes, str, str], Awaitable[tuple[Part, ...]]]

PLAIN      = "text/plain"
PDF        = "application/pdf"
MEDIA      = ("image/", "audio/", "video/")
EXECUTABLE = (
    b"MZ", b"\x7fELF", b"#!", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
)
SIGNATURES = (
    (b"%PDF-", 0, PDF), (b"\x89PNG\r\n\x1a\n", 0, "image/png"), (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"GIF87a", 0, "image/gif"), (b"GIF89a", 0, "image/gif"), (b"WEBP", 8, "image/webp"), (b"WAVE", 8, "audio/wav"),
    (b"ID3", 0, "audio/mpeg"), (b"\xff\xfb", 0, "audio/mpeg"), (b"OggS", 0, "audio/ogg"), (b"fLaC", 0, "audio/flac"),
    (b"ftypM4A", 4, "audio/mp4"), (b"ftyp", 4, "video/mp4"), (b"\x1aE\xdf\xa3", 0, "video/webm"),
    (b"PK\x03\x04", 0, "application/zip"),
)
WORKER     = """
import io, json, resource, sys
resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
from pypdf import PdfReader
reader = PdfReader(io.BytesIO(sys.stdin.buffer.read()), strict=True)
pages, chars, total, found = int(sys.argv[1]), int(sys.argv[2]), 0, []
if reader.is_encrypted or len(reader.pages) > pages: sys.exit(2)
for number, page in enumerate(reader.pages, 1):
    text = page.extract_text(extraction_mode="layout")
    total += len(text)
    if total > chars: sys.exit(3)
    found.append({"page": number, "text": text})
sys.stdout.write(json.dumps(found, ensure_ascii=False))
"""

@dataclass(frozen=True, slots=True)
class ExtractPolicy:

    max_bytes : int = 16 * 1024 * 1024
    max_chars : int = 500_000
    max_pages : int = 200
    seconds   : float = 30.0
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

    def text ( self ) -> str:

        return "\n\n".join(part.text for part in self.parts)

class Extraction:

    def sniff ( self, data: bytes ) -> str:

        if data.startswith(EXECUTABLE): raise Fault(Code.VALIDATION, reason="file.type")

        for mark, offset, mime in SIGNATURES:

            if data[offset:offset + len(mark)] == mark: return mime

        if b"\x00" in data: raise Fault(Code.VALIDATION, reason="file.type")

        try: data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error: raise Fault(Code.VALIDATION, reason="file.encoding") from error

        return PLAIN

    def read ( self, path: str | Path, policy: ExtractPolicy ) -> tuple[str, bytes, str]:

        target = Path(path).expanduser()

        try: handle = self.opened(target, policy.root)
        except OSError as error: raise Fault(Code.FORBIDDEN, reason="file.path") from error

        if not stat.S_ISREG(os.fstat(handle).st_mode):

            os.close(handle)

            raise Fault(Code.FORBIDDEN, reason="file.regular")

        with os.fdopen(handle, "rb") as stream: data = stream.read(policy.max_bytes + 1)

        if len(data) > policy.max_bytes: raise Fault(Code.VALIDATION, reason="file.size")

        return target.name, data, self.sniff(data)

    def opened ( self, target: Path, allowed: str | None ) -> int:

        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

        if allowed is None: return os.open(target, flags)

        root = Path(allowed).expanduser().resolve()

        try: parts = target.absolute().relative_to(root).parts
        except ValueError as error: raise Fault(Code.FORBIDDEN, reason="file.root") from error

        if not parts or ".." in parts: raise Fault(Code.FORBIDDEN, reason="file.root")

        folder = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

        try:

            for part in parts[:-1]:

                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)

                os.close(folder)

                folder = child

            return os.open(parts[-1], flags, dir_fd=folder)

        finally: os.close(folder)

    async def extract (
        self, path: str | Path, policy: ExtractPolicy | None = None, converter: Converter | None = None,
    ) -> Extracted:

        chosen = policy or ExtractPolicy()
        name, data, _ = await thread.offload(self.read, path, chosen)

        return await self.parse(name, data, chosen, converter)

    async def parse (
        self, name: str, data: bytes, policy: ExtractPolicy | None = None, converter: Converter | None = None,
    ) -> Extracted:

        chosen = policy or ExtractPolicy()

        if len(data) > chosen.max_bytes: raise Fault(Code.VALIDATION, reason="file.size")

        mime = self.sniff(data)

        if mime == PLAIN: return self.bounded(Extracted(name, mime, (Part(data.decode("utf-8")),)), chosen)
        if mime == PDF:

            found = await self.pdf(data, chosen)

            if any(part.text.strip() for part in found): return self.bounded(Extracted(name, mime, found), chosen)

        if converter is None or not (mime == PDF or mime.startswith(MEDIA)):
            raise Fault(Code.VALIDATION, reason="file.converter")

        converted = await thread.timeout(converter(data, mime, name), chosen.seconds, "file.conversion.timeout")

        if not any(part.text.strip() for part in converted):
            raise Fault(Code.VALIDATION, reason="file.conversion.empty")

        return self.bounded(Extracted(name, mime, converted), chosen)

    async def pdf ( self, data: bytes, policy: ExtractPolicy ) -> tuple[Part, ...]:

        argv         = [sys.executable, "-I", "-c", WORKER, str(policy.max_pages), str(policy.max_chars)]
        code, output = await thread.command(argv, data, policy.seconds, policy.max_chars * 8 + 65_536)

        if code != 0: raise Fault(Code.VALIDATION, reason="file.pdf")

        return tuple(Part(str(row["text"]), int(row["page"])) for row in json.loads(output))

    def bounded ( self, extracted: Extracted, policy: ExtractPolicy ) -> Extracted:

        if sum(len(part.text) for part in extracted.parts) > policy.max_chars:
            raise Fault(Code.VALIDATION, reason="file.text")

        return extracted
