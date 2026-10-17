from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

class SocketConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="SOCKET_")

    enabled     : bool  = True
    path        : str   = "/ws"
    connections : int   = Field(default=10_000, ge=1)
    queue       : int   = Field(default=256, ge=8)
    frame       : int   = Field(default=64 * 1024, ge=512)
    ping        : float = Field(default=25.0, gt=0, le=300)
    drops       : int   = Field(default=64, ge=1)
