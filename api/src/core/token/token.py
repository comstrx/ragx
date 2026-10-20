from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from core.crypto import ApiKey, crypto
from core.date import date
from core.error import Code, Fault
from core.rand import rand
import base64, binascii, jwt

RESERVED   = frozenset({"sub", "jti", "iat", "exp", "iss", "kind", "nbf", "aud"})
SYMMETRIC  = frozenset({"HS256", "HS384", "HS512"})
ASYMMETRIC = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"})
MINIMUM    = 32
REQUIRED   = ["sub", "jti", "kind", "iat", "exp", "iss"]

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

    def age ( self ) -> float:

        return max((date.now() - self.issued).total_seconds(), 0.0)

    def get ( self, name: str, default: Any = None ) -> Any:

        return self.extra.get(name, default)

    def is_kind ( self, *kinds: str ) -> bool:

        return self.kind in kinds

    def dump ( self ) -> dict[str, Any]:

        return {
            "subject": self.subject, "kind": self.kind, "id": self.id, "issued": date.iso(self.issued),
            "expires": date.iso(self.expires), "extra": dict(self.extra),
        }

class Adapter(Protocol):

    def issue ( self, claims: Claims ) -> str: ...

    def verify ( self, text: str ) -> Claims: ...

    def peek ( self, text: str ) -> Claims: ...

class JwtAdapter:

    def __init__ (
        self, secret: str, algorithm: str = "HS256", issuer: str = "api", leeway: int = 5, public: str | None = None,
        audience: str | None = None,
    ) -> None:

        if algorithm not in SYMMETRIC | ASYMMETRIC: raise Fault(Code.INTERNAL, reason="token.algorithm")
        if algorithm in SYMMETRIC and len(secret) < MINIMUM: raise Fault(Code.INTERNAL, reason="token.secret")
        if algorithm in ASYMMETRIC and not public: raise Fault(Code.INTERNAL, reason="token.public")

        self._secret    = secret
        self._public    = public or secret
        self._algorithm = algorithm
        self._issuer    = issuer
        self._leeway    = leeway
        self._audience  = audience

    def issue ( self, claims: Claims ) -> str:

        payload: dict[str, Any] = {
            **{ key: value for key, value in claims.extra.items() if key not in RESERVED },
            "sub"  : claims.subject,
            "jti"  : claims.id,
            "kind" : claims.kind,
            "iat"  : int(claims.issued.timestamp()),
            "exp"  : int(claims.expires.timestamp()),
            "iss"  : self._issuer,
        }

        if self._audience: payload["aud"] = self._audience

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify ( self, text: str ) -> Claims:

        try:

            payload = jwt.decode(
                text, self._public, algorithms=[self._algorithm], issuer=self._issuer, leeway=self._leeway,
                audience=self._audience, options={ "require": REQUIRED, "verify_aud": self._audience is not None },
            )

        except jwt.ExpiredSignatureError as error: raise Fault(Code.UNAUTHORIZED, reason="token.expired") from error
        except jwt.InvalidTokenError as error: raise Fault(Code.UNAUTHORIZED, reason="token") from error

        return self.claims_of(payload)

    def peek ( self, text: str ) -> Claims:

        try: payload = jwt.decode(text, options={ "verify_signature": False, "verify_exp": False })
        except jwt.InvalidTokenError as error: raise Fault(Code.UNAUTHORIZED, reason="token") from error

        return self.claims_of(payload)

    def claims_of ( self, payload: dict[str, Any] ) -> Claims:

        return Claims(
            subject=str(payload.get("sub", "")),
            kind=str(payload.get("kind", "")),
            id=str(payload.get("jti", "")),
            issued=datetime.fromtimestamp(int(payload.get("iat", 0)), UTC),
            expires=datetime.fromtimestamp(int(payload.get("exp", 0)), UTC),
            extra={ key: value for key, value in payload.items() if key not in RESERVED },
        )

    def describe ( self ) -> dict[str, object]:

        return {
            "algorithm": self._algorithm, "issuer": self._issuer, "leeway": self._leeway, "audience": self._audience,
        }

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

        if ttl <= 0: raise Fault(Code.INTERNAL, reason="token.ttl")

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

    def basic ( self, header: str | None ) -> tuple[str, str]:

        scheme, _, text = (header or "").strip().partition(" ")

        try: decoded = base64.b64decode(text.strip(), validate=True).decode()
        except (binascii.Error, UnicodeDecodeError) as error:
            raise Fault(Code.UNAUTHORIZED, reason="token.basic") from error

        name, colon, secret = decoded.partition(":")

        if scheme.lower() != "basic" or not colon or not name or not secret:
            raise Fault(Code.UNAUTHORIZED, reason="token.basic")

        return name, secret

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
