from typing import Literal

from core.config import Settings, field

type Driver = Literal["local", "rabbitmq"]

class EventConfig(Settings, env_prefix="EVENT_"):

    driver   : Driver = "local"
    url      : str    = "amqp://guest:guest@127.0.0.1:5672/"
    exchange : str    = "events"
    queue    : str    = ""
    prefetch : int    = field(32, ge=1, le=10_000)
