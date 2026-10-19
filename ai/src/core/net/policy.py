from collections.abc import Mapping

RETRYABLE = frozenset({408, 500, 502, 504})
REJECTED  = frozenset({425, 429, 503})
SAFE      = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
KEYS      = ("idempotency-key", "paypal-request-id", "x-idempotency-key")
CAP       = 30.0

def repeatable_of ( method: str, headers: Mapping[str, str] | None ) -> bool:

    named = { name.lower() for name in (headers or {}) }

    return method.upper() in SAFE or any(key in named for key in KEYS)

def pause_of ( header: str | None, fallback: float ) -> float:

    if header and header.strip().isdigit(): return min(float(header.strip()), CAP)

    return fallback
