from collections.abc import Mapping
from typing import Any

from .cast import Cast
from .probe import Probe
from .text import Text
from .units import Units
from .web import Web

class Parse(Cast, Units, Probe, Text, Web):

    def at ( self, data: Mapping[str, Any], key: str, default: object = None ) -> object:

        return self.incoming(data, key, default)

    def integer_at ( self, data: Mapping[str, Any], key: str, default: int = 0 ) -> int:

        return self.integer(self.incoming(data, key, default), default)

    def bool_at ( self, data: Mapping[str, Any], key: str, default: bool = False ) -> bool:

        found = self.incoming(data, key, None)

        return default if found is None else self.bool(found)

    def text_at ( self, data: Mapping[str, Any], key: str, default: str = "" ) -> str:

        found = self.incoming(data, key, None)

        return default if found is None else self.text(found)

    def list_at ( self, data: Mapping[str, Any], key: str ) -> list[Any]:

        return self.list(self.incoming(data, key, None))

    def dict_at ( self, data: Mapping[str, Any], key: str ) -> dict[str, Any]:

        return self.dict(self.incoming(data, key, None))

    def typed ( self, value: object, kind: str, default: object = None ) -> object:

        match kind:
            case "str" | "string" | "text": return self.text(value) if value is not None else default
            case "int" | "integer": return self.integer(value, self.integer(default))
            case "float" | "number": return self.float(value, self.float(default))
            case "bool" | "boolean": return self.bool(value) if value is not None else self.bool(default)
            case "list" | "array": return self.list(value) if value is not None else self.list(default)
            case "dict" | "object" | "json": return self.dict(value) if value is not None else self.dict(default)
            case "duration": return self.duration(value, self.duration(default))
            case "bytes" | "size": return self.bytes(value, self.bytes(default))
            case "percent": return self.percent(value, self.percent(default))
            case _: return value if value is not None else default

    def many ( self, data: Mapping[str, Any], shape: Mapping[str, str] ) -> dict[str, Any]:

        return { key: self.typed(self.incoming(data, key, None), kind) for key, kind in shape.items() }
