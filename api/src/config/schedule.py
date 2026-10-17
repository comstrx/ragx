from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

class ScheduleConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="SCHEDULE_")

    enabled  : bool  = True
    tick     : float = Field(default=1.0, gt=0, le=60)
    timezone : str   = "UTC"
