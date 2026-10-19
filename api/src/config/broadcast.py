from typing import Literal

from core.config import Settings, field

type Driver = Literal["local", "redis"]

class BroadcastConfig(Settings, env_prefix="BROADCAST_"):

    enabled     : bool   = True
    driver      : Driver = "local"
    url         : str    = "redis://127.0.0.1:6379/0"
    topic       : str    = "broadcast"
    socket      : bool   = field(default=True, env="SOCKET_ENABLED")
    path        : str    = field("/ws", env="SOCKET_PATH")
    connections : int    = field(10_000, env="SOCKET_CONNECTIONS", ge=1)
    outbox      : int    = field(256, env="SOCKET_QUEUE", ge=8)
    frame       : int    = field(64 * 1024, env="SOCKET_FRAME", ge=512)
    ping        : float  = field(25.0, env="SOCKET_PING", gt=0, le=300)
    drops       : int    = field(64, env="SOCKET_DROPS", ge=1)
