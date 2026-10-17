from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings
from core.fs import Path

YEAR = 31_536_000

class AssetsConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="ASSETS_")

    folder    : str  = "src/public"
    url       : str  = "/assets"
    cache     : int  = Field(default=YEAR, ge=0)
    versioned : bool = True

    def path ( self, base: Path ) -> Path:

        folder = Path(self.folder)

        return (folder if folder.is_absolute() else base / folder).resolve()
