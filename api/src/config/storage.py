from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings

MEBIBYTE = 1024 * 1024

class StorageConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    disk        : str = "public"
    url         : str = "/storage"
    pattern     : str = "{Y}/{m}/{d}"
    max_size    : int = Field(default=10 * MEBIBYTE, ge=1)
    allowed     : list[str] = Field(default_factory=list)
    s3_bucket   : str = ""
    s3_region   : str = ""
    s3_endpoint : str = ""
    s3_key      : str = ""
    s3_secret   : str = ""
    s3_prefix   : str = ""
    s3_url      : str = ""
    s3_path_style : bool = False
