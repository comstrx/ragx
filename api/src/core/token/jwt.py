from datetime import UTC, datetime
from typing import Any

from core.error import Code, Fault
from .claims import Claims
import jwt

RESERVED   = frozenset({"sub", "jti", "iat", "exp", "iss", "kind", "nbf", "aud"})
SYMMETRIC  = frozenset({"HS256", "HS384", "HS512"})
ASYMMETRIC = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"})
MINIMUM    = 32
REQUIRED   = ["sub", "jti", "kind", "iat", "exp", "iss"]

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
