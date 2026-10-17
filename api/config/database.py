from typing import Literal
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type SslMode = Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"]


class DatabaseConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="DB_")

    host        : str     = "127.0.0.1"
    port        : int     = Field(default=5432, ge=1, le=65535)
    database    : str     = "ragx"
    username    : str     = "ragx"
    password    : str     = ""
    sslmode     : SslMode = "prefer"
    search_path : str     = "public"
    pool_min    : int     = Field(default=1, ge=0, le=64)
    pool_max    : int     = Field(default=10, ge=1, le=256)
    timeout     : float   = Field(default=5.0, gt=0, le=120)
    migrate     : bool    = True
    seed        : bool    = False

    def url ( self ) -> str:

        auth = quote(self.username, safe="")
        if self.password: auth += ":" + quote(self.password, safe="")

        return f"postgresql://{auth}@{self.host}:{self.port}/{self.database}?sslmode={self.sslmode}"
