from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from engine.error import Code, Fault
from engine.parse import parse
from dotenv import dotenv_values
import builtins, os

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

    def files ( self, root: Path, mode: str ) -> builtins.list[Path]:

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

    def is_ ( self, *modes: str ) -> builtins.bool:

        return any(self._mode in self.aliases(mode) or self._mode == mode for mode in modes)

    def local ( self ) -> builtins.bool:

        return self.is_("local")

    def testing ( self ) -> builtins.bool:

        return self.is_("testing")

    def production ( self ) -> builtins.bool:

        return self.is_("production")

    def root ( self ) -> Path | None:

        return self._root

    def loaded ( self ) -> tuple[Path, ...]:

        return self._files

    def get ( self, key: str, default: str | None = None ) -> str | None:

        return os.environ.get(key, default)

    def require ( self, key: str ) -> str:

        found = os.environ.get(key)

        if found is None or found == "": raise Fault(Code.INTERNAL, reason=f"env.{key}")

        return found

    def set ( self, key: str, item: object ) -> None:

        os.environ[key] = parse.text(item)

    def remove ( self, key: str ) -> builtins.bool:

        return os.environ.pop(key, None) is not None

    def has ( self, key: str ) -> builtins.bool:

        return key in os.environ

    def all ( self, prefix: str = "" ) -> dict[str, str]:

        return { key: item for key, item in os.environ.items() if key.startswith(prefix) }

    @contextmanager
    def scoped ( self, **values: object ) -> Iterator[None]:

        previous = { key: os.environ.get(key) for key in values }

        for key, item in values.items():

            if item is None: os.environ.pop(key, None)
            else: os.environ[key] = parse.text(item)

        try: yield
        finally:

            for key, item in previous.items():

                if item is None: os.environ.pop(key, None)
                else: os.environ[key] = item

    def text ( self, key: str, default: str = "" ) -> str:

        found = os.environ.get(key)

        return default if found is None else found

    def bool ( self, key: str, default: builtins.bool = False ) -> builtins.bool:

        found = os.environ.get(key)

        return default if found is None else parse.bool(found)

    def int ( self, key: str, default: builtins.int = 0 ) -> builtins.int:

        return parse.integer(os.environ.get(key), default)

    def float ( self, key: str, default: builtins.float = 0.0 ) -> builtins.float:

        return parse.float(os.environ.get(key), default)

    def list (
        self, key: str, default: Mapping[str, object] | builtins.list[object] | None = None,
    ) -> builtins.list[object]:

        found = os.environ.get(key)

        return parse.list(found) if found else list(default or [])
