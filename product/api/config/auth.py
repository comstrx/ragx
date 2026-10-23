from typing import ClassVar

from engine.config import Settings, field

class AuthConfig(Settings, env_prefix="AUTH_"):

    hidden: ClassVar[tuple[str, ...]] = ("secret", "keys")

    secret      : str = ""
    algorithm   : str = "HS256"
    issuer      : str = "ragx"
    access_ttl  : int = field(900, ge=60, le=86400)
    refresh_ttl : int = field(2_592_000, ge=3600, le=31_536_000)
    keys        : list[str] = field(factory=list)
