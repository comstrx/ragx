from typing import Literal

from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["local"]

class BroadcastConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="BROADCAST_")

    enabled : bool   = True
    driver  : Driver = "local"
