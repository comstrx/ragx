from collections.abc import AsyncIterator

from core.error import Code, Fault
import hashlib, hmac

HASHES = ("sha256", "sha512", "sha3_256", "blake2b", "blake2s")
SHORT  = 12

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
