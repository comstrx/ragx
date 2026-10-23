from typing import ClassVar

from engine.config import Settings, field
from engine.fs import Path

MEBIBYTE = 1024 * 1024
YEAR     = 31_536_000
BLOCKED  = (
    "html", "htm", "xhtml", "svg", "js", "mjs", "php", "phar", "sh", "bash", "bat", "cmd", "exe", "dll", "com", "msi",
    "jar", "py", "pl", "rb",
)

class StorageConfig(Settings, env_prefix="STORAGE_"):

    hidden: ClassVar[tuple[str, ...]] = ("s3_key", "s3_secret")

    disk          : str  = "public"
    root          : str  = "storage"
    public        : str  = "app/public"
    private       : str  = "app/private"
    logs          : str  = "logs"
    url           : str  = "/storage"
    pattern       : str  = "{Y}/{m}/{d}"
    max_size      : int  = field(10 * MEBIBYTE, ge=1)
    allowed       : list[str] = field(factory=list)
    blocked       : list[str] = field(factory=lambda: list(BLOCKED))
    s3_bucket     : str  = ""
    s3_region     : str  = ""
    s3_endpoint   : str  = ""
    s3_key        : str  = ""
    s3_secret     : str  = ""
    s3_prefix     : str  = ""
    s3_url        : str  = ""
    s3_path_style : bool = False
    assets        : str  = field("public", env="ASSETS_FOLDER")
    assets_url    : str  = field("/assets", env="ASSETS_URL")
    assets_cache  : int  = field(YEAR, env="ASSETS_CACHE", ge=0)
    versioned     : bool = field(default=True, env="ASSETS_VERSIONED")

    def resolve ( self, base: Path, part: str ) -> Path:

        root = (base / self.root).resolve()

        return (Path(part) if Path(part).is_absolute() else root / part).resolve()

    def public_path ( self, base: Path ) -> Path:

        return self.resolve(base, self.public)

    def private_path ( self, base: Path ) -> Path:

        return self.resolve(base, self.private)

    def logs_path ( self, base: Path ) -> Path:

        return self.resolve(base, self.logs)

    def assets_path ( self, base: Path ) -> Path:

        folder = Path(self.assets)

        return (folder if folder.is_absolute() else base / folder).resolve()
