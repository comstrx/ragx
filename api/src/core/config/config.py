from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from core.log import masked
from core.parse import parse
from .settings import Settings

type Overrides = dict[str, object]

MISSING = object()

class Config:

    def __init__ ( self ) -> None:

        self._models: dict[str, Settings] = {}
        self._overrides: Overrides = {}

    def register[S: Settings] ( self, name: str, kind: type[S] ) -> S:

        known = self._models.get(name)

        if isinstance(known, kind): return known

        loaded = kind.load()

        self._models[name] = loaded

        return loaded

    def of[S: Settings] ( self, name: str, kind: type[S] ) -> S:

        known = self._models.get(name)

        if not isinstance(known, kind): raise KeyError(name)

        return known

    def names ( self ) -> list[str]:
        return sorted(self._models)

    def get ( self, key: str, default: Any = None ) -> Any:

        if key in self._overrides: return self._overrides[key]

        name, _, rest = key.partition(".")
        current: object = self._models.get(name)

        if current is None: return default
        if not rest: return current

        for part in rest.split("."):

            if isinstance(current, BaseModel) and part in type(current).model_fields: current = getattr(current, part)
            elif isinstance(current, Mapping) and part in current: current = current[part]
            else: return default

        return current

    def require ( self, key: str ) -> Any:

        found = self.get(key, MISSING)

        if found is MISSING: raise KeyError(key)

        return found

    def has ( self, key: str ) -> bool:
        return self.get(key, MISSING) is not MISSING

    def set ( self, key: str, item: object ) -> None:
        self._overrides[key] = item

    def remove ( self, key: str ) -> bool:
        return self._overrides.pop(key, MISSING) is not MISSING

    def integer ( self, key: str, default: int = 0 ) -> int:
        return parse.integer(self.get(key, default), default)

    def number ( self, key: str, default: float = 0.0 ) -> float:
        return parse.float(self.get(key, default), default)

    def flag ( self, key: str, default: bool = False ) -> bool:

        found = self.get(key, None)

        return default if found is None else parse.bool(found)

    def text ( self, key: str, default: str = "" ) -> str:

        found = self.get(key, None)

        return default if found is None else parse.text(found)

    def items ( self, key: str ) -> list[Any]:
        return parse.list(self.get(key, None))

    def duration ( self, key: str, default: float = 0.0 ) -> float:
        return parse.duration(self.get(key, default), default)

    def redacted ( self ) -> dict[str, Any]:

        snapshot: dict[str, Any] = masked(self.all())

        return snapshot

    def all ( self ) -> dict[str, Any]:

        snapshot: dict[str, Any] = { name: model.model_dump() for name, model in self._models.items() }

        for key, item in self._overrides.items():

            name, _, rest = key.partition(".")

            if not rest: snapshot[name] = item
            else: snapshot.setdefault(name, {})[rest] = item

        return snapshot

    def reset ( self ) -> None:

        self._models.clear()
        self._overrides.clear()
