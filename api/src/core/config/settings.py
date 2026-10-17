from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", frozen=True, env_nested_delimiter="__")

    @classmethod
    def load ( cls ) -> Self:
        return cls()
