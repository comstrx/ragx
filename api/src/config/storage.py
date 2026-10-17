from pydantic import Field
from pydantic_settings import SettingsConfigDict
from core.config import Settings
from core.fs import Path

MEBIBYTE = 1024 * 1024
BLOCKED  = [
    "html", "htm", "xhtml", "svg", "js", "mjs", "php", "phar", "sh", "bash", "bat", "cmd", "exe", "dll", "com", "msi",
    "jar", "py", "pl", "rb",
]

class StorageConfig(Settings):

    model_config = SettingsConfigDict(env_prefix="STORAGE_")

    disk        : str = "public"
    root        : str = "src/storage"
    public      : str = "app/public"
    private     : str = "app/private"
    logs        : str = "logs"
    url         : str = "/storage"
    pattern     : str = "{Y}/{m}/{d}"
    max_size    : int = Field(default=10 * MEBIBYTE, ge=1)
    allowed     : list[str] = Field(default_factory=list)
    blocked     : list[str] = Field(default_factory=lambda: list(BLOCKED))
    s3_bucket   : str = ""
    s3_region   : str = ""
    s3_endpoint : str = ""
    s3_key      : str = ""
    s3_secret   : str = ""
    s3_prefix   : str = ""
    s3_url      : str = ""
    s3_path_style : bool = False

    def resolve ( self, base: Path, part: str ) -> Path:

        root = (base / self.root).resolve()

        return (Path(part) if Path(part).is_absolute() else root / part).resolve()

    def public_path ( self, base: Path ) -> Path:
        return self.resolve(base, self.public)

    def private_path ( self, base: Path ) -> Path:
        return self.resolve(base, self.private)

    def logs_path ( self, base: Path ) -> Path:
        return self.resolve(base, self.logs)
