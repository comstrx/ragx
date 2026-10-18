from pathlib import Path

from .base import Pathish
import mimetypes

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
