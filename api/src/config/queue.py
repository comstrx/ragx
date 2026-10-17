from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["memory", "sync", "rabbitmq"]

class QueueConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="QUEUE_")

    driver   : Driver = "memory"
    url      : str    = "amqp://guest:guest@127.0.0.1:5672/"
    exchange : str    = "jobs"
    prefetch : int    = Field(default=16, ge=1, le=10_000)
    workers  : int    = Field(default=2, ge=0, le=64)
    tries    : int    = Field(default=3, ge=1, le=20)
    backoff  : float  = Field(default=1.0, ge=0, le=3600)
    queues   : list[str] = Field(default_factory=lambda: ["default"])
