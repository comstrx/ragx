from pathlib import Path
from core.error import Code, Fault
import hashlib, shutil, tarfile, tempfile

MAX_MEMBERS = 4096

class Bundle:

    def members ( self, bundle: tarfile.TarFile, root: Path, limit: int ) -> list[tarfile.TarInfo]:

        members = bundle.getmembers()
        if sum(member.size for member in members) > limit or len(members) > MAX_MEMBERS:
            raise Fault(Code.VALIDATION, reason="bundle.limit")
        names = [(root / member.name).absolute() for member in members]
        if len(set(names)) != len(names): raise Fault(Code.VALIDATION, reason="bundle.duplicate")
        for member in members:
            target = (root / member.name).resolve()
            if not target.is_relative_to(root) or member.isdev() or member.isfifo():
                raise Fault(Code.FORBIDDEN, reason="bundle.path")
            if member.issym() or member.islnk():
                link = (target.parent / member.linkname).resolve() if member.issym() else (
                    root / member.linkname
                ).resolve()
                if not link.is_relative_to(root): raise Fault(Code.FORBIDDEN, reason="bundle.link")
        return members

    def verify ( self, archive: Path, root: Path, limit: int ) -> None:

        with tarfile.open(archive, "r:gz") as bundle:
            members = self.members(bundle, root, limit)
            expected_paths: set[Path] = set()
            for member in members:
                target = root / member.name
                expected_paths.add(target)
                expected_paths.update(parent for parent in target.parents if parent.is_relative_to(root))
            if any(path not in expected_paths for path in root.rglob("*")):
                raise Fault(Code.VALIDATION, reason="bundle.extra")
            for member in members: self.verify_member(bundle, member, root)

    def verify_member ( self, bundle: tarfile.TarFile, member: tarfile.TarInfo, root: Path ) -> None:

        target = root / member.name
        if member.isdir():
            if not target.is_dir() or target.is_symlink(): raise Fault(Code.VALIDATION, reason="bundle.integrity")
            return
        if member.issym():
            if not target.is_symlink() or str(target.readlink()) != member.linkname:
                raise Fault(Code.VALIDATION, reason="bundle.integrity")
            return
        expected_size = bundle.getmember(member.linkname).size if member.islnk() else member.size
        if not target.is_file() or target.is_symlink() or target.stat().st_size != expected_size:
            raise Fault(Code.VALIDATION, reason="bundle.integrity")
        original = bundle.extractfile(member)
        if original is None: raise Fault(Code.VALIDATION, reason="bundle.integrity")
        with original, target.open("rb") as stream:
            expected = hashlib.sha256()
            while block := original.read(256 * 1024): expected.update(block)
            if expected.digest() != hashlib.file_digest(stream, "sha256").digest():
                raise Fault(Code.VALIDATION, reason="bundle.integrity")

    def unpack ( self, archive: Path, destination: Path, limit: int = 256 * 1024 * 1024 ) -> Path:

        if destination.is_symlink(): raise Fault(Code.FORBIDDEN, reason="bundle.path")
        destination = destination.resolve()
        if destination.exists():
            self.verify(archive, destination, limit)
            return destination

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".unpack-", dir=destination.parent))
        try:
            with tarfile.open(archive, "r:gz") as bundle:
                self.members(bundle, temporary, limit)
                bundle.extractall(temporary, filter="data")
            temporary.replace(destination)
            return destination
        finally:
            if temporary.exists(): shutil.rmtree(temporary)

    def executable ( self, root: Path, name: str ) -> Path:

        found = [path for path in root.rglob(name) if path.is_file() and path.resolve().is_relative_to(root.resolve())]
        if len(found) != 1: raise Fault(Code.VALIDATION, reason="bundle.executable")
        found[0].chmod(0o700)
        return found[0]
