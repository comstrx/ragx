from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

class AuthConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="AUTH_")

    secret      : str = ""
    algorithm   : str = "HS256"
    issuer      : str = "ragx"
    access_ttl  : int = Field(default=900, ge=60, le=86400)
    refresh_ttl : int = Field(default=2_592_000, ge=3600, le=31_536_000)
    keys        : list[str] = Field(default_factory=list)
