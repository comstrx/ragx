from pathlib import Path

from core.error import Fault
from core.fs import fs
from .cipher import Cipher
from .digest import Digest
from .keys import Keys
from .password import Password

class Crypto(Cipher, Digest, Keys):

    def __init__ ( self ) -> None:

        super().__init__()

        self.password = Password()

    def hash ( self, secret: str ) -> str:
        return self.password.hash(secret)

    def verify ( self, secret: str, hashed: str ) -> bool:
        return self.password.verify(secret, hashed)

    def stale ( self, hashed: str ) -> bool:
        return self.password.stale(hashed)

    async def seal_file ( self, source: Path | str, target: Path | str | None = None ) -> Path:

        sealed = self.seal(await fs.read_bytes(source))

        return await fs.write_text(target or f"{source}.sealed", sealed)

    async def open_file ( self, source: Path | str, target: Path | str, ttl: int | None = None ) -> Path:
        return await fs.write_bytes(target, self.open(await fs.read_text(source), ttl))

    def is_sealed ( self, token: str ) -> bool:

        try: self.open(token)
        except Fault: return False

        return True
