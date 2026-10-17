from typing import Literal

from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

type Driver = Literal["smtp", "log", "memory"]

class MailConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="MAIL_")

    driver   : Driver = "log"
    host     : str    = "127.0.0.1"
    port     : int    = Field(default=587, ge=1, le=65535)
    username : str | None = None
    password : str | None = None
    tls      : bool   = True
    ssl      : bool   = False
    verify   : bool   = True
    timeout  : float  = Field(default=10.0, gt=0, le=120)
    sender   : str    = "hello@ragx.test"
    name     : str    = "RagX"
