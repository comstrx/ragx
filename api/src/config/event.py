from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["local", "rabbitmq"]

class EventConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="EVENT_")

    driver   : Driver = "local"
    url      : str    = "amqp://guest:guest@127.0.0.1:5672/"
    exchange : str    = "events"
    queue    : str    = ""
    prefetch : int    = Field(default=32, ge=1, le=10_000)
