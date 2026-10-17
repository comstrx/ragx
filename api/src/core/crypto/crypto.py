from collections.abc import Sequence

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from core.exceptions import Code, Fault
import hashlib, hmac

HASHES = ("sha256", "sha512", "blake2b")

class Crypto:

    def __init__ ( self ) -> None:

        self._hasher = PasswordHasher()
        self._cipher: MultiFernet | None = None

    def setup ( self, keys: Sequence[str] ) -> None:

        if not keys: raise Fault(Code.INTERNAL, reason="crypto.keys")

        self._cipher = MultiFernet([Fernet(key.encode()) for key in keys])

    def ready ( self ) -> bool:
        return self._cipher is not None

    def key ( self ) -> str:
        return Fernet.generate_key().decode()

    def hash ( self, secret: str ) -> str:
        return self._hasher.hash(secret)

    def verify ( self, secret: str, hashed: str ) -> bool:

        try: return self._hasher.verify(hashed, secret)
        except (VerifyMismatchError, VerificationError, InvalidHashError): return False

    def stale ( self, hashed: str ) -> bool:

        try: return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError: return True

    def seal ( self, data: str | bytes ) -> str:

        if self._cipher is None: raise Fault(Code.INTERNAL, reason="crypto")

        return self._cipher.encrypt(data.encode() if isinstance(data, str) else data).decode()

    def open ( self, token: str, ttl: int | None = None ) -> bytes:

        if self._cipher is None: raise Fault(Code.INTERNAL, reason="crypto")

        try: return self._cipher.decrypt(token.encode(), ttl=ttl)
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def open_text ( self, token: str, ttl: int | None = None ) -> str:
        return self.open(token, ttl).decode()

    def rotate ( self, token: str ) -> str:

        if self._cipher is None: raise Fault(Code.INTERNAL, reason="crypto")

        try: return self._cipher.rotate(token.encode()).decode()
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def digest ( self, data: str | bytes, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise ValueError(algorithm)

        return hashlib.new(algorithm, data.encode() if isinstance(data, str) else data).hexdigest()

    def sign ( self, data: str | bytes, key: str | bytes, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise ValueError(algorithm)

        raw = data.encode() if isinstance(data, str) else data
        pin = key.encode() if isinstance(key, str) else key

        return hmac.new(pin, raw, algorithm).hexdigest()

    def compare ( self, left: str | bytes, right: str | bytes ) -> bool:

        a = left.encode() if isinstance(left, str) else left
        b = right.encode() if isinstance(right, str) else right

        return hmac.compare_digest(a, b)
