from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from core.parse import parse
import os

MODES   = { "local": ("local",), "testing": ("testing", "test"), "production": ("production", "prod") }
DEFAULT = "local"
SWITCH  = "APP_ENV"

class Env:

    def __init__ ( self ) -> None:

        self._root: Path | None = None
        self._mode  = DEFAULT
        self._files: tuple[Path, ...] = ()

    def load ( self, root: Path, mode: str | None = None ) -> str:

        base   = self.read(root / ".env")
        chosen = (mode or os.environ.get(SWITCH) or base.get(SWITCH) or DEFAULT).lower()
        layers = self.files(root, chosen)
        merged: dict[str, str] = {}

        for path in layers: merged.update(self.read(path))

        for key, item in merged.items(): os.environ.setdefault(key, item)

        os.environ.setdefault(SWITCH, chosen)

        self._root  = root
        self._mode  = chosen
        self._files = tuple(layers)

        return chosen

    def files ( self, root: Path, mode: str ) -> list[Path]:

        aliases = self.aliases(mode)
        layers  = [*(f".env.{alias}" for alias in aliases)]
        secrets = [*(f".secret.{alias}" for alias in aliases)]
        names   = [".env", *layers, ".secret", *secrets]

        return [root / name for name in names if (root / name).is_file()]

    def aliases ( self, mode: str ) -> tuple[str, ...]:
        return MODES.get(mode, (mode,))

    def read ( self, path: Path ) -> dict[str, str]:

        if not path.is_file(): return {}

        return { key: item for key, item in dotenv_values(path).items() if item is not None }

    def mode ( self ) -> str:
        return self._mode

    def root ( self ) -> Path | None:
        return self._root

    def loaded ( self ) -> tuple[Path, ...]:
        return self._files

    def get ( self, key: str, default: str | None = None ) -> str | None:
        return os.environ.get(key, default)

    def require ( self, key: str ) -> str:

        found = os.environ.get(key)

        if found is None or found == "": raise KeyError(key)

        return found

    def set ( self, key: str, item: object ) -> None:
        os.environ[key] = parse.text(item)

    def remove ( self, key: str ) -> bool:
        return os.environ.pop(key, None) is not None

    def has ( self, key: str ) -> bool:
        return key in os.environ

    def all ( self, prefix: str = "" ) -> dict[str, str]:
        return { key: item for key, item in os.environ.items() if key.startswith(prefix) }

    def bool ( self, key: str, default: bool = False ) -> bool:

        found = os.environ.get(key)

        return default if found is None else parse.bool(found)

    def int ( self, key: str, default: int = 0 ) -> int:
        return parse.integer(os.environ.get(key), default)

    def float ( self, key: str, default: float = 0.0 ) -> float:
        return parse.float(os.environ.get(key), default)

    def list ( self, key: str, default: Mapping[str, object] | list[object] | None = None ) -> list[object]:

        found = os.environ.get(key)

        return parse.list(found) if found else list(default or [])
