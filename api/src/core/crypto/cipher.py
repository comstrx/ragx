from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from core.error import Code, Fault
from core.json import json
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64, hashlib, secrets

LENGTH     = 32
ITERATIONS = 600_000
PREFIX     = "rk"

@dataclass(frozen=True, slots=True)
class ApiKey:

    id          : str
    secret      : str
    fingerprint : str

    def header ( self ) -> str:

        return f"{self.id}.{self.secret}"

    def dump ( self ) -> dict[str, str]:

        return { "id": self.id, "fingerprint": self.fingerprint }

class Keys:

    def generate ( self ) -> str:

        return Fernet.generate_key().decode()

    def random ( self, size: int = LENGTH ) -> bytes:

        return secrets.token_bytes(size)

    def random_text ( self, size: int = LENGTH ) -> str:

        return secrets.token_urlsafe(size)

    def derive ( self, secret: str | bytes, salt: str | bytes, length: int = LENGTH, info: bytes = b"" ) -> bytes:

        material = secret.encode() if isinstance(secret, str) else secret
        grain    = salt.encode() if isinstance(salt, str) else salt

        return HKDF(algorithm=hashes.SHA256(), length=length, salt=grain, info=info).derive(material)

    def stretch ( self, secret: str, salt: bytes, length: int = LENGTH, iterations: int = ITERATIONS ) -> bytes:

        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=length, salt=salt, iterations=iterations)

        return kdf.derive(secret.encode())

    def fernet_from ( self, secret: str, salt: str | bytes ) -> str:

        return base64.urlsafe_b64encode(self.derive(secret, salt)).decode()

    def pair ( self, prefix: str = PREFIX ) -> ApiKey:

        identity = f"{prefix}_{secrets.token_hex(8)}"
        secret   = secrets.token_urlsafe(LENGTH)

        return ApiKey(identity, secret, self.fingerprint(secret))

    def fingerprint ( self, secret: str ) -> str:

        return hashlib.sha256(secret.encode()).hexdigest()

    def matches ( self, secret: str, fingerprint: str ) -> bool:

        return secrets.compare_digest(self.fingerprint(secret), fingerprint)

    def split ( self, header: str ) -> tuple[str, str]:

        identity, _, secret = header.strip().partition(".")

        return identity, secret

class Cipher:

    def __init__ ( self ) -> None:

        self._cipher: MultiFernet | None = None
        self._count = 0

    def setup ( self, keys: Sequence[str] ) -> None:

        if not keys: raise Fault(Code.INTERNAL, reason="crypto.keys")

        try: self._cipher = MultiFernet([Fernet(key.encode()) for key in keys])
        except ValueError as error: raise Fault(Code.INTERNAL, reason="crypto.key") from error

        self._count = len(keys)

    def ready ( self ) -> bool:

        return self._cipher is not None

    def key ( self ) -> str:

        return Fernet.generate_key().decode()

    def _engine_ ( self ) -> MultiFernet:

        if self._cipher is None: raise Fault(Code.INTERNAL, reason="crypto")

        return self._cipher

    def seal ( self, data: str | bytes ) -> str:

        return self._engine_().encrypt(data.encode() if isinstance(data, str) else data).decode()

    def open ( self, token: str, ttl: int | None = None ) -> bytes:

        try: return self._engine_().decrypt(token.encode(), ttl=ttl)
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def open_text ( self, token: str, ttl: int | None = None ) -> str:

        return self.open(token, ttl).decode()

    def seal_json ( self, value: object ) -> str:

        return self.seal(json.encode(value))

    def open_json ( self, token: str, ttl: int | None = None ) -> Any:

        return json.loads(self.open(token, ttl))

    def rotate ( self, token: str ) -> str:

        try: return self._engine_().rotate(token.encode()).decode()
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def stamp ( self, token: str ) -> int:

        try: return self._engine_().extract_timestamp(token.encode())
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def describe ( self ) -> dict[str, object]:

        return { "ready": self.ready(), "keys": self._count }
