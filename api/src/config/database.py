from typing import ClassVar, Literal

from core.config import Settings, field

type SslMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]

class DatabaseConfig(Settings, env_prefix="DB_"):

    hidden: ClassVar[tuple[str, ...]] = ("password",)

    driver      : str     = "postgresql"
    host        : str     = "127.0.0.1"
    port        : int     = field(5432, ge=1, le=65535)
    database    : str     = "ragx"
    username    : str     = "ragx"
    password    : str     = ""
    sslmode     : SslMode = "prefer"
    search_path : str     = "public"
    pool_min    : int     = field(4, ge=0, le=64)
    pool_max    : int     = field(10, ge=1, le=256)
    timeout     : float   = field(5.0, gt=0, le=120)
    migrate     : bool    = True
    seed        : bool    = False
