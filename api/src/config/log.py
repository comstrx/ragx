from typing import Literal

from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Level    = Literal["debug", "info", "warning", "error", "critical"]
type Renderer = Literal["console", "json"]

class LogConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level    : Level    = "info"
    renderer : Renderer = "console"
