from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict
from core.config import Settings
from app.enums import Mode

class AppConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="APP_")

    name    : str  = "RagX"
    version : str  = "0.1.0"
    env     : Mode = Mode.LOCAL
    debug   : bool = False
    host    : str  = "127.0.0.1"
    port    : int  = Field(default=8000, ge=1, le=65535)
    workers : int  = Field(default=1, ge=1, le=64)
    prefix  : str  = "/v1"
    release : str | None = None
    origins : list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:3001"])

    @field_validator("release", mode="before")
    @classmethod
    def blank_release_is_none ( cls, value: object ) -> object:
        return value or None
