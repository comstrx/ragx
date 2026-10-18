from pathlib import Path

type Pathish = str | Path

CHUNK    = 64 * 1024
FALLBACK = "application/octet-stream"

def as_path ( target: Pathish ) -> Path:
    return target if isinstance(target, Path) else Path(target)

def posix ( target: Pathish ) -> str:
    return as_path(target).as_posix()

def extension_of ( target: Pathish ) -> str:
    return as_path(target).suffix.lstrip(".").lower()
