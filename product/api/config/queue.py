from typing import Literal

from engine.config import Settings, field

type Driver = Literal["memory", "sync", "rabbitmq"]

class QueueConfig(Settings, env_prefix="QUEUE_"):

    driver   : Driver = "memory"
    url      : str    = "amqp://guest:guest@127.0.0.1:5672/"
    exchange : str    = "jobs"
    prefetch : int    = field(16, ge=1, le=10_000)
    workers  : int    = field(2, ge=0, le=64)
    tries    : int    = field(3, ge=1, le=20)
    backoff  : float  = field(1.0, ge=0, le=3600)
    queues   : list[str] = field(factory=lambda: ["default"])
    schedule : bool   = field(default=True, env="SCHEDULE_ENABLED")
    tick     : float  = field(1.0, env="SCHEDULE_TICK", gt=0, le=60)
