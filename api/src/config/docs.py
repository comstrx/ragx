from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Theme = Literal[
    "default", "alternate", "moon", "purple", "solarized", "bluePlanet", "saturn", "kepler", "mars", "deepSpace",
    "laserwave", "none",
]
type Layout = Literal["modern", "classic"]

class DocsConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="DOCS_")

    enabled     : bool   = True
    path        : str    = "/docs"
    openapi     : str    = "/openapi.json"
    title       : str    = ""
    description : str    = ""
    theme       : Theme  = "default"
    layout      : Layout = "modern"
    dark        : bool   = True
    sidebar     : bool   = True
    models      : bool   = True
    download    : bool   = True
    search      : bool   = True
    errors      : bool   = True
    servers     : list[str] = Field(default_factory=list)
    tags        : list[str] = Field(default_factory=list)
    hide        : list[str] = Field(default_factory=list)
