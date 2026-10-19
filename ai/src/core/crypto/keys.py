from dataclasses import dataclass

from cryptography.fernet import Fernet
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
