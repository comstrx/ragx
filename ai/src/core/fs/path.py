from pathlib import Path, PurePosixPath

from core.error import Code, Fault
from .base import Pathish
import os, re, tempfile

UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
DOTS   = re.compile(r"\.{2,}")

class Paths:

    def path ( self, *parts: Pathish ) -> Path:

        return Path(*parts)

    def name ( self, target: Pathish ) -> str:

        return Path(target).name

    def stem ( self, target: Pathish ) -> str:

        return Path(target).stem

    def extension ( self, target: Pathish ) -> str:

        return Path(target).suffix.lstrip(".").lower()

    def parent ( self, target: Pathish ) -> Path:

        return Path(target).parent

    def join ( self, base: Pathish, *parts: Pathish ) -> Path:

        return Path(base).joinpath(*parts)

    def resolve ( self, target: Pathish ) -> Path:

        return Path(target).resolve()

    def normalize ( self, target: Pathish ) -> str:

        return PurePosixPath(str(target).replace("\\", "/")).as_posix()

    def relative ( self, base: Pathish, target: Pathish ) -> Path:

        return Path(target).resolve().relative_to(Path(base).resolve())

    def within ( self, base: Pathish, target: Pathish ) -> bool:

        try: Path(target).resolve().relative_to(Path(base).resolve())
        except ValueError: return False

        return True

    def segments ( self, target: Pathish ) -> list[str]:

        return [part for part in PurePosixPath(self.normalize(target)).parts if part not in ("", "/", ".")]

    def clean ( self, target: str ) -> str:

        parts  = self.segments(target)
        unsafe = not parts or any(part == ".." or part.startswith(".") for part in parts)

        if unsafe: raise Fault(Code.BAD_REQUEST, reason="fs.path")

        return "/".join(parts)

    def safe_name ( self, name: str, fallback: str = "file" ) -> str:

        plain = DOTS.sub(".", UNSAFE.sub("-", name.strip())).strip("-.")

        return plain or fallback

    def with_extension ( self, target: Pathish, extension: str ) -> Path:

        return Path(target).with_suffix(f".{extension.lstrip('.')}" if extension else "")

    def with_name ( self, target: Pathish, name: str ) -> Path:

        return Path(target).with_name(name)

    def is_hidden ( self, target: Pathish ) -> bool:

        return Path(target).name.startswith(".")

    def is_absolute ( self, target: Pathish ) -> bool:

        return Path(target).is_absolute()

    def unique ( self, target: Pathish ) -> Path:

        path  = Path(target)
        found = path
        index = 1

        while found.exists():

            found  = path.with_name(f"{path.stem}-{index}{path.suffix}")
            index += 1

        return found

    def home ( self ) -> Path:

        return Path.home()

    def cwd ( self ) -> Path:

        return Path.cwd()

    def temp ( self ) -> Path:

        return Path(tempfile.gettempdir())

    def expand ( self, target: Pathish ) -> Path:

        return Path(os.path.expandvars(str(Path(target).expanduser())))

    def depth ( self, base: Pathish, target: Pathish ) -> int:

        return len(self.relative(base, target).parts)

    def common ( self, *targets: Pathish ) -> Path:

        return Path(os.path.commonpath([str(Path(target).resolve()) for target in targets]))

    def join_lines ( self, lines: list[str] | tuple[str, ...] ) -> str:

        return "\n".join(lines) + "\n"
