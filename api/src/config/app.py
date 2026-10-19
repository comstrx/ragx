from core.config import Settings, field
from app.enums import Mode

PROXIES = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
ORIGINS = ("http://localhost:3000", "http://localhost:3001")

class AppConfig(Settings, env_prefix="APP_"):

    name    : str  = "RagX"
    version : str  = "0.1.0"
    env     : Mode = Mode.LOCAL
    debug   : bool = False
    host    : str  = "127.0.0.1"
    port    : int  = field(8000, ge=1, le=65535)
    workers : int  = field(1, ge=1, le=64)
    prefix  : str  = "/v1"
    url     : str  = ""
    release : str | None = None
    origins : list[str] = field(factory=lambda: list(ORIGINS))
    proxies : list[str] = field(factory=lambda: list(PROXIES))
