from datetime import timedelta

from core.crypto import ApiKey, crypto
from core.date import date
from core.error import Code, Fault
from core.rand import rand
from .claims import Adapter, Claims

class Token:

    def __init__ ( self ) -> None:

        self._adapter: Adapter | None = None

    def setup ( self, adapter: Adapter ) -> None:
        self._adapter = adapter

    def ready ( self ) -> bool:
        return self._adapter is not None

    def engine ( self ) -> Adapter:

        if self._adapter is None: raise Fault(Code.INTERNAL, reason="token")

        return self._adapter

    def issue ( self, subject: str, kind: str = "access", ttl: int = 900, **extra: object ) -> tuple[str, Claims]:

        if ttl <= 0: raise ValueError(ttl)

        now    = date.now()
        claims = Claims(subject, kind, str(rand.uuid()), now, now + timedelta(seconds=ttl), dict(extra))

        return self.engine().issue(claims), claims

    def pair (
        self, subject: str, access_ttl: int = 900, refresh_ttl: int = 2_592_000, **extra: object,
    ) -> dict[str, object]:

        access, access_claims   = self.issue(subject, "access", access_ttl, **extra)
        refresh, refresh_claims = self.issue(subject, "refresh", refresh_ttl, **extra)

        return {
            "access": access, "refresh": refresh, "access_expires": date.iso(access_claims.expires),
            "refresh_expires": date.iso(refresh_claims.expires), "refresh_id": refresh_claims.id,
        }

    def verify ( self, text: str, kind: str | None = None ) -> Claims:

        claims = self.engine().verify(text.strip())

        if kind is not None and claims.kind != kind: raise Fault(Code.UNAUTHORIZED, reason="token.kind")
        if not claims.alive(): raise Fault(Code.UNAUTHORIZED, reason="token.expired")

        return claims

    def peek ( self, text: str ) -> Claims:
        return self.engine().peek(text.strip())

    def fingerprint ( self, text: str ) -> str:
        return crypto.digest(text.strip())

    def bearer ( self, header: str | None ) -> str:

        scheme, _, text = (header or "").strip().partition(" ")

        if scheme.lower() != "bearer" or not text.strip(): raise Fault(Code.UNAUTHORIZED, reason="token.missing")

        return text.strip()

    def maybe_bearer ( self, header: str | None ) -> str | None:

        scheme, _, text = (header or "").strip().partition(" ")

        return text.strip() if scheme.lower() == "bearer" and text.strip() else None

    def api_key ( self, prefix: str = "rk" ) -> ApiKey:
        return crypto.pair(prefix)

    def api_key_matches ( self, secret: str, fingerprint: str ) -> bool:
        return crypto.matches(secret, fingerprint)

    def api_key_split ( self, header: str ) -> tuple[str, str]:
        return crypto.split(header)
