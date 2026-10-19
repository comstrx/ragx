from pathlib import Path
from core.error import Code, Fault
import os, tempfile

def atomic_bytes ( target: Path, data: bytes ) -> Path:

    if target.is_symlink(): raise Fault(Code.FORBIDDEN, reason="file.symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + target.name + ".", suffix=".part", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(target)
        folder = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(folder)
        finally: os.close(folder)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)
