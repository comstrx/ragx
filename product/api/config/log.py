from typing import Literal

from engine.config import Settings

type Level    = Literal["debug", "info", "warning", "error", "critical"]
type Renderer = Literal["console", "json"]

class LogConfig(Settings, env_prefix="LOG_"):

    level    : Level    = "info"
    renderer : Renderer = "console"
    file     : str      = ""
