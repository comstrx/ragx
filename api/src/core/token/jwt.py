from datetime import UTC, datetime

from core.exceptions import Code, Fault
from .token import Claims
import jwt

RESERVED  = frozenset({"sub", "jti", "iat", "exp", "iss", "kind", "nbf", "aud"})
SYMMETRIC = frozenset({"HS256", "HS384", "HS512"})
MINIMUM   = 32

class JwtAdapter:

    def __init__ (
        self, secret: str, algorithm: str = "HS256", issuer: str = "api", leeway: int = 5, public: str | None = None,
    ) -> None:

        if algorithm in SYMMETRIC and len(secret) < MINIMUM: raise Fault(Code.INTERNAL, reason="token.secret")

        self._secret    = secret
        self._public    = public or secret
        self._algorithm = algorithm
        self._issuer    = issuer
        self._leeway    = leeway

    def issue ( self, claims: Claims ) -> str:

        payload = {
            **{ key: value for key, value in claims.extra.items() if key not in RESERVED },
            "sub"  : claims.subject,
            "jti"  : claims.id,
            "kind" : claims.kind,
            "iat"  : int(claims.issued.timestamp()),
            "exp"  : int(claims.expires.timestamp()),
            "iss"  : self._issuer,
        }

        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify ( self, text: str ) -> Claims:

        try:

            payload = jwt.decode(
                text, self._public, algorithms=[self._algorithm], issuer=self._issuer, leeway=self._leeway,
                options={ "require": ["sub", "jti", "kind", "iat", "exp", "iss"] },
            )

        except jwt.ExpiredSignatureError as error: raise Fault(Code.UNAUTHORIZED, reason="token.expired") from error
        except jwt.InvalidTokenError as error: raise Fault(Code.UNAUTHORIZED, reason="token") from error

        return Claims(
            subject=str(payload["sub"]),
            kind=str(payload["kind"]),
            id=str(payload["jti"]),
            issued=datetime.fromtimestamp(int(payload["iat"]), UTC),
            expires=datetime.fromtimestamp(int(payload["exp"]), UTC),
            extra={ key: value for key, value in payload.items() if key not in RESERVED },
        )
