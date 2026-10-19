from typing import Literal

from core.config import Settings, field

type Driver = Literal["memory", "redis"]

class CacheConfig(Settings, env_prefix="CACHE_"):

    driver : Driver = "memory"
    url    : str    = "redis://127.0.0.1:6379/0"
    prefix : str    = "ragx"
    ttl    : float  = field(300.0, gt=0)
