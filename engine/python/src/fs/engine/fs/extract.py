from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from engine.error import Code, Fault
from engine.json import json
from engine.thread import thread
import base64, mimetypes, os, stat, sys

type Lack = Literal["ocr", "vision", "speech", "frames"]

PLAIN      = "text/plain"
PDF        = "application/pdf"
VISUAL     = ("image/", "audio/", "video/")
READER     = Path(__file__).with_name("reader.py")
MEDIA      = Path(__file__).with_name("media.py")
SPARE      = 65_536
BYTERATE   = 32_000
WIDE       = 8
CALM       = { "LANG": "C.UTF-8", "OMP_NUM_THREADS": "1", "RAYON_NUM_THREADS": "2" }
EXECUTABLE = (
    b"MZ", b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
)
SIGNATURES = (
    (b"%PDF-", 0, PDF), (b"\x89PNG\r\n\x1a\n", 0, "image/png"), (b"\xff\xd8\xff", 0, "image/jpeg"),
    (b"GIF87a", 0, "image/gif"), (b"GIF89a", 0, "image/gif"), (b"WEBP", 8, "image/webp"), (b"BM", 0, "image/bmp"),
    (b"II*\x00", 0, "image/tiff"), (b"MM\x00*", 0, "image/tiff"), (b"WAVE", 8, "audio/wav"),
    (b"AVI ", 8, "video/x-msvideo"), (b"ID3", 0, "audio/mpeg"), (b"\xff\xfb", 0, "audio/mpeg"),
    (b"\xff\xf3", 0, "audio/mpeg"), (b"\xff\xf1", 0, "audio/aac"), (b"OggS", 0, "audio/ogg"),
    (b"fLaC", 0, "audio/flac"), (b"#!AMR", 0, "audio/amr"), (b"ftypM4A", 4, "audio/mp4"),
    (b"ftypheic", 4, "image/heic"), (b"ftypavif", 4, "image/avif"), (b"ftypqt", 4, "video/quicktime"),
    (b"ftyp", 4, "video/mp4"), (b"\x1aE\xdf\xa3", 0, "video/webm"), (b"{\\rtf", 0, "application/rtf"),
    (b"PK\x03\x04", 0, "application/zip"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", 0, "application/x-ole-storage"),
)
TEXTUAL    = {
    ".md": "text/markdown", ".markdown": "text/markdown", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".eml": "message/rfc822", ".yaml": "application/x-yaml", ".yml": "application/x-yaml", ".rst": "text/x-rst",
    ".org": "text/x-org", ".tex": "application/x-latex",
}
BOOT       = """
import resource, runpy, sys
memory, seconds = int(sys.argv[2]), int(sys.argv[3])
resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.argv = [sys.argv[1], *sys.argv[4:]]
runpy.run_path(sys.argv[0], run_name="__main__")
"""

@dataclass(frozen=True, slots=True)
class ExtractPolicy:

    max_bytes  : int = 16 * 1024 * 1024
    max_chars  : int = 500_000
    max_pages  : int = 200
    seconds    : float = 30.0
    memory     : int = 1024 * 1024 * 1024
    duration   : float = 4 * 3600.0
    pixels     : int = 40_000_000
    root       : str | None = None

    def __post_init__ ( self ) -> None:

        limits = (self.max_bytes, self.max_chars, self.max_pages, self.seconds, self.memory, self.duration, self.pixels)

        if min(limits) <= 0: raise Fault(Code.VALIDATION, reason="file.limits")

@dataclass(frozen=True, slots=True)
class Part:

    text   : str
    page   : int | None = None
    second : float | None = None

@dataclass(frozen=True, slots=True)
class Gap:

    kind  : Lack
    page  : int | None = None
    start : float | None = None
    end   : float | None = None

@dataclass(frozen=True, slots=True)
class Frame:

    second : float
    data   : bytes
    mime   : str = "image/jpeg"

@dataclass(frozen=True, slots=True)
class Extracted:

    source : str
    mime   : str
    parts  : tuple[Part, ...]
    gaps   : tuple[Gap, ...] = ()

    def text ( self ) -> str:

        return "\n\n".join(part.text for part in self.parts)

    def complete ( self ) -> bool:

        return not self.gaps

class Extraction:

    def sniff ( self, data: bytes, name: str = "" ) -> str:

        if data.startswith(EXECUTABLE) or (data.startswith(b"#!") and not data.startswith(b"#!AMR")):
            raise Fault(Code.VALIDATION, reason="file.type")

        for mark, offset, mime in SIGNATURES:

            if data[offset:offset + len(mark)] == mark: return mime

        if b"\x00" in data[:8192]: raise Fault(Code.VALIDATION, reason="file.type")

        return self.textual(data, name)

    def textual ( self, data: bytes, name: str ) -> str:

        head   = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        suffix = Path(name).suffix.lower()

        if head.startswith((b"<!doctype html", b"<html")): return "text/html"
        if head.startswith(b"<?xml"): return "application/xml"
        if suffix in TEXTUAL: return TEXTUAL[suffix]

        guessed = mimetypes.guess_type(name)[0] or ""

        return guessed if guessed.startswith("text/") or guessed in ("application/json", "application/xml") else PLAIN

    def read ( self, path: str | Path, policy: ExtractPolicy ) -> tuple[str, bytes, str]:

        target = Path(path).expanduser()

        try: handle = self.opened(target, policy.root)
        except OSError as error: raise Fault(Code.FORBIDDEN, reason="file.path") from error

        if not stat.S_ISREG(os.fstat(handle).st_mode):

            os.close(handle)

            raise Fault(Code.FORBIDDEN, reason="file.regular")

        with os.fdopen(handle, "rb") as stream: data = stream.read(policy.max_bytes + 1)

        if len(data) > policy.max_bytes: raise Fault(Code.VALIDATION, reason="file.size")

        return target.name, data, self.sniff(data, target.name)

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

    async def extract ( self, path: str | Path, policy: ExtractPolicy | None = None ) -> Extracted:

        chosen = policy or ExtractPolicy()
        name, data, _ = await thread.offload(self.read, path, chosen)

        return await self.parse(name, data, chosen)

    async def parse ( self, name: str, data: bytes, policy: ExtractPolicy | None = None ) -> Extracted:

        chosen = policy or ExtractPolicy()

        if len(data) > chosen.max_bytes: raise Fault(Code.VALIDATION, reason="file.size")

        mime = self.sniff(data, name)

        if mime == PLAIN and (plain := self.plain(data)) is not None:
            return self.bounded(Extracted(name, mime, (Part(plain),) if plain.strip() else ()), chosen)

        script  = MEDIA if mime.startswith(VISUAL) else READER
        limits  = {
            "mime": mime, "chars": chosen.max_chars, "pages": chosen.max_pages, "duration": chosen.duration,
            "pixels": chosen.pixels,
        }
        found   = json.loads(await self.run(script, "read", data, chosen, limits, chosen.max_chars * WIDE + SPARE))
        parts   = tuple(Part(str(row["text"]), row.get("page"), row.get("second")) for row in found["parts"])
        gaps    = tuple(Gap(row["kind"], row.get("page"), row.get("start"), row.get("end")) for row in found["gaps"])

        return self.bounded(Extracted(name, str(found["mime"]), parts, gaps), chosen)

    def plain ( self, data: bytes ) -> str | None:

        try: return data.decode("utf-8-sig")
        except UnicodeDecodeError: return None

    async def render ( self, data: bytes, page: int, policy: ExtractPolicy | None = None, scale: float = 2.0 ) -> bytes:

        chosen = policy or ExtractPolicy()

        return await self.run(READER, "render", data, chosen, { "page": page, "scale": scale }, chosen.pixels * 4)

    async def clip ( self, data: bytes, start: float, end: float, policy: ExtractPolicy | None = None ) -> bytes:

        chosen = policy or ExtractPolicy()

        if not 0 <= start < end: raise Fault(Code.VALIDATION, reason="file.clip")

        size = int((end - start) * BYTERATE) + SPARE

        return await self.run(MEDIA, "clip", data, chosen, { "start": start, "end": end }, size)

    async def still ( self, data: bytes, policy: ExtractPolicy | None = None ) -> bytes:

        chosen = policy or ExtractPolicy()

        return await self.run(MEDIA, "still", data, chosen, { "pixels": chosen.pixels }, chosen.max_bytes + SPARE)

    async def frames (
        self, data: bytes, moments: tuple[float, ...], policy: ExtractPolicy | None = None,
    ) -> tuple[Frame, ...]:

        chosen = policy or ExtractPolicy()
        found  = json.loads(await self.run(MEDIA, "frames", data, chosen, { "moments": moments }, chosen.pixels))

        return tuple(Frame(float(row["second"]), base64.b64decode(row["data"])) for row in found)

    async def run (
        self, script: Path, action: str, data: bytes, policy: ExtractPolicy, limits: dict[str, Any], output: int,
    ) -> bytes:

        boot = [sys.executable, "-I", "-c", BOOT, str(script), str(policy.memory), str(int(policy.seconds) + 1)]
        argv = [*boot, action, json.dumps(limits)]

        try: code, found = await thread.command(argv, data, policy.seconds, output, CALM)
        except Fault as fault:
            raise Fault(Code.VALIDATION, reason=f"file.{(fault.reason or 'broken').rsplit('.', 1)[-1]}") from fault

        if code == 0: return found

        try: reason = str(json.loads(found)["error"])
        except (Fault, KeyError, TypeError): reason = "broken"

        raise Fault(Code.VALIDATION, reason=f"file.{reason}")

    def bounded ( self, extracted: Extracted, policy: ExtractPolicy ) -> Extracted:

        if sum(len(part.text) for part in extracted.parts) > policy.max_chars:
            raise Fault(Code.VALIDATION, reason="file.text")

        return extracted
