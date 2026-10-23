from typing import Literal

from engine.config import Settings, field

type Theme = Literal[
    "default", "alternate", "moon", "purple", "solarized", "bluePlanet", "saturn", "kepler", "mars", "deepSpace",
    "laserwave", "none",
]
type Layout = Literal["modern", "classic"]

class DocsConfig(Settings, env_prefix="DOCS_"):

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
    servers     : list[str] = field(factory=list)
    tags        : list[str] = field(factory=list)
    hide        : list[str] = field(factory=list)
