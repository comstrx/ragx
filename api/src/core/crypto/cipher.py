from collections.abc import Sequence
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from core.error import Code, Fault
from core.json import json

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

    def engine ( self ) -> MultiFernet:

        if self._cipher is None: raise Fault(Code.INTERNAL, reason="crypto")

        return self._cipher

    def seal ( self, data: str | bytes ) -> str:
        return self.engine().encrypt(data.encode() if isinstance(data, str) else data).decode()

    def open ( self, token: str, ttl: int | None = None ) -> bytes:

        try: return self.engine().decrypt(token.encode(), ttl=ttl)
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def open_text ( self, token: str, ttl: int | None = None ) -> str:
        return self.open(token, ttl).decode()

    def seal_json ( self, value: object ) -> str:
        return self.seal(json.encode(value))

    def open_json ( self, token: str, ttl: int | None = None ) -> Any:
        return json.loads(self.open(token, ttl))

    def rotate ( self, token: str ) -> str:

        try: return self.engine().rotate(token.encode()).decode()
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def stamp ( self, token: str ) -> int:

        try: return self.engine().extract_timestamp(token.encode())
        except InvalidToken as error: raise Fault(Code.BAD_REQUEST, reason="cipher") from error

    def describe ( self ) -> dict[str, object]:
        return { "ready": self.ready(), "keys": self._count }
