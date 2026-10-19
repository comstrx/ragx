from collections.abc import AsyncIterator
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from core.error import Code, Fault
from core.fs import fs
from .cipher import Cipher, Keys
import hashlib, hmac

HASHES = ("sha256", "sha512", "sha3_256", "blake2b", "blake2s")
SHORT  = 12

class Password:

    def __init__ ( self, time_cost: int = 3, memory_cost: int = 65536, parallelism: int = 4 ) -> None:

        self._hasher = PasswordHasher(time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism)

    def hash ( self, secret: str ) -> str:

        return self._hasher.hash(secret)

    def verify ( self, secret: str, hashed: str ) -> bool:

        try: return self._hasher.verify(hashed, secret)
        except (VerifyMismatchError, VerificationError, InvalidHashError): return False

    def stale ( self, hashed: str ) -> bool:

        try: return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError: return True

    def is_hash ( self, text: str ) -> bool:

        return text.startswith("$argon2")

    def describe ( self ) -> dict[str, int]:

        return {
            "time_cost": self._hasher.time_cost, "memory_cost": self._hasher.memory_cost,
            "parallelism": self._hasher.parallelism,
        }

def raw ( data: str | bytes ) -> bytes:

    return data.encode() if isinstance(data, str) else data

class Digest:

    def digest ( self, data: str | bytes, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise Fault(Code.INTERNAL, reason=f"crypto.algorithm.{algorithm}")

        return hashlib.new(algorithm, raw(data)).hexdigest()

    def digest_bytes ( self, data: str | bytes, algorithm: str = "sha256" ) -> bytes:

        if algorithm not in HASHES: raise Fault(Code.INTERNAL, reason=f"crypto.algorithm.{algorithm}")

        return hashlib.new(algorithm, raw(data)).digest()

    async def digest_stream ( self, chunks: AsyncIterator[bytes], algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise Fault(Code.INTERNAL, reason=f"crypto.algorithm.{algorithm}")

        hasher = hashlib.new(algorithm)

        async for chunk in chunks: hasher.update(chunk)

        return hasher.hexdigest()

    def fingerprint ( self, data: str | bytes, size: int = SHORT ) -> str:

        return self.digest(data)[:size]

    def sign ( self, data: str | bytes, key: str | bytes, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise Fault(Code.INTERNAL, reason=f"crypto.algorithm.{algorithm}")

        return hmac.new(raw(key), raw(data), algorithm).hexdigest()

    def verify_signature (
        self, data: str | bytes, key: str | bytes, signature: str, algorithm: str = "sha256",
    ) -> bool:

        return hmac.compare_digest(self.sign(data, key, algorithm), signature)

    def compare ( self, left: str | bytes, right: str | bytes ) -> bool:

        return hmac.compare_digest(raw(left), raw(right))

    def checksum ( self, data: str | bytes ) -> str:

        return hashlib.blake2b(raw(data), digest_size=16).hexdigest()

    def algorithms ( self ) -> tuple[str, ...]:

        return HASHES

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
