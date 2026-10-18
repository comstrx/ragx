from typing import Literal

from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["local", "redis"]

class BroadcastConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="BROADCAST_")

    enabled : bool   = True
    driver  : Driver = "local"
    url     : str    = "redis://127.0.0.1:6379/0"
    topic   : str    = "broadcast"
