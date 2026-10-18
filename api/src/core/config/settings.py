from typing import Any, Self

from pydantic_settings import BaseSettings, SettingsConfigDict
from core.log import masked

class Settings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", frozen=True, env_nested_delimiter="__")

    @classmethod
    def load ( cls ) -> Self:
        return cls()

    @classmethod
    def env_prefix ( cls ) -> str:
        return str(cls.model_config.get("env_prefix", ""))

    def describe ( self ) -> dict[str, Any]:

        plain: dict[str, Any] = masked(self.model_dump())

        return plain
