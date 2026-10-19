from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from core.error import Code, Fault
import anyio, fcntl, hashlib, os, tempfile

DIGEST_LENGTH = 64

@dataclass(frozen=True, slots=True)
class Artifact:

    sha256 : str
    size   : int
    name   : str

    def __post_init__ ( self ) -> None:

        if len(self.sha256) != DIGEST_LENGTH or any(c not in "0123456789abcdef" for c in self.sha256):
            raise Fault(Code.VALIDATION, reason="artifact.digest")
        if self.size <= 0 or Path(self.name).name != self.name or self.name in (".", ".."):
            raise Fault(Code.VALIDATION, reason="artifact.descriptor")

class Artifacts:

    def __init__ ( self, root: str | Path ) -> None:

        self.root = Path(root).expanduser().resolve()

    def target ( self, artifact: Artifact ) -> Path:

        target = self.root / artifact.sha256 / artifact.name

        if target.is_symlink() or not target.resolve().is_relative_to(self.root):
            raise Fault(Code.FORBIDDEN, reason="artifact.path")

        return target

    @asynccontextmanager
    async def lock ( self, key: str, wait: float = 120.0 ) -> AsyncIterator[None]:

        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.root / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)

        try:
            with anyio.fail_after(wait):
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError: await anyio.sleep(0.05)
            yield
        except TimeoutError as error:
            raise Fault(Code.UNAVAILABLE, reason="artifact.lock.timeout") from error
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def valid ( self, artifact: Artifact ) -> bool:

        target = self.target(artifact)

        if not target.is_file() or target.stat().st_size != artifact.size: return False

        with target.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == artifact.sha256

    async def install ( self, artifact: Artifact, source: Callable[[], AsyncIterator[bytes]] ) -> Path:

        async with self.lock(artifact.sha256, wait=900):

            if await anyio.to_thread.run_sync(self.valid, artifact): return self.target(artifact)

            target = self.target(artifact)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor, temporary = tempfile.mkstemp(prefix=".partial-", dir=target.parent)
            digest = hashlib.sha256()
            size = 0

            try:
                async with await anyio.open_file(descriptor, "wb") as stream:
                    async for chunk in source():
                        size += len(chunk)
                        if size > artifact.size: raise Fault(Code.VALIDATION, reason="artifact.size")
                        digest.update(chunk)
                        await stream.write(chunk)
                    await stream.flush()
                    await anyio.to_thread.run_sync(os.fsync, stream.wrapped.fileno())

                if size != artifact.size or digest.hexdigest() != artifact.sha256:
                    raise Fault(Code.VALIDATION, reason="artifact.integrity")

                await anyio.Path(temporary).replace(target)
                parent = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(parent)
                finally: os.close(parent)

                return target
            finally:
                await anyio.Path(temporary).unlink(missing_ok=True)
