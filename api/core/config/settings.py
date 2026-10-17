from pathlib import Path
from typing import Self

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(extra="ignore", frozen=True, env_file_encoding="utf-8", env_nested_delimiter="__")

    @classmethod
    def load ( cls, root: Path, files: tuple[str, ...] = (".env", ".secret") ) -> Self:
        return cls(_env_file=tuple(root / name for name in files))
