from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["memory", "redis"]

class CacheConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="CACHE_")

    driver : Driver = "memory"
    url    : str    = "redis://127.0.0.1:6379/0"
    prefix : str    = "ragx"
    ttl    : float  = Field(default=300.0, gt=0)
