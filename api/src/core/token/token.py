from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from core.crypto import crypto
from core.date import date
from core.exceptions import Code, Fault
from core.rand import rand

@dataclass(frozen=True, slots=True)
class Claims:

    subject : str
    kind    : str
    id      : str
    issued  : datetime
    expires : datetime
    extra   : Mapping[str, object] = field(default_factory=dict)

    def remaining ( self ) -> float:
        return max((self.expires - date.now()).total_seconds(), 0.0)

    def alive ( self ) -> bool:
        return self.expires > date.now()

class Adapter(Protocol):

    def issue ( self, claims: Claims ) -> str: ...

    def verify ( self, text: str ) -> Claims: ...

class Token:

    def __init__ ( self ) -> None:

        self._adapter: Adapter | None = None

    def setup ( self, adapter: Adapter ) -> None:
        self._adapter = adapter

    def ready ( self ) -> bool:
        return self._adapter is not None

    def issue ( self, subject: str, kind: str = "access", ttl: int = 900, **extra: object ) -> tuple[str, Claims]:

        if ttl <= 0: raise ValueError(ttl)

        now    = date.now()
        claims = Claims(subject, kind, str(rand.uuid()), now, now + timedelta(seconds=ttl), dict(extra))

        return self._engine_().issue(claims), claims

    def verify ( self, text: str, kind: str | None = None ) -> Claims:

        claims = self._engine_().verify(text.strip())

        if kind is not None and claims.kind != kind: raise Fault(Code.UNAUTHORIZED, reason="token.kind")
        if not claims.alive(): raise Fault(Code.UNAUTHORIZED, reason="token.expired")

        return claims

    def fingerprint ( self, text: str ) -> str:
        return crypto.digest(text.strip())

    def bearer ( self, header: str | None ) -> str:

        scheme, _, text = (header or "").strip().partition(" ")

        if scheme.lower() != "bearer" or not text.strip(): raise Fault(Code.UNAUTHORIZED, reason="token.missing")

        return text.strip()

    def _engine_ ( self ) -> Adapter:

        if self._adapter is None: raise Fault(Code.INTERNAL, reason="token")

        return self._adapter
