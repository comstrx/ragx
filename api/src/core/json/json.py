from collections.abc import Mapping
from decimal import Decimal
from enum import Enum
from typing import Any

from core.exceptions import Code, Fault
import orjson

type JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
type Text = str | bytes | bytearray | memoryview

OPENERS = ("{", "[", '"', b"{", b"[", b'"')
MISSING = object()

class Json:

    def dumps ( self, value: object, pretty: bool = False, sort: bool = False, lenient: bool = False ) -> str:
        return self.encode(value, pretty, sort, lenient).decode()

    def encode ( self, value: object, pretty: bool = False, sort: bool = False, lenient: bool = False ) -> bytes:

        option   = orjson.OPT_NON_STR_KEYS
        option  |= (orjson.OPT_INDENT_2 if pretty else 0) | (orjson.OPT_SORT_KEYS if sort else 0)
        fallback = self.loose if lenient else self.fallback

        return orjson.dumps(value, default=fallback, option=option)

    def pretty ( self, value: object ) -> str:
        return self.dumps(value, pretty=True)

    def loads ( self, text: Text ) -> Any:

        try: return orjson.loads(text)
        except orjson.JSONDecodeError as error: raise Fault(Code.BAD_REQUEST, reason="json") from error

    def parse ( self, text: object, default: object = None ) -> Any:

        if not isinstance(text, str | bytes | bytearray): return default

        try: return orjson.loads(text)
        except orjson.JSONDecodeError: return default

    def valid ( self, text: object ) -> bool:

        if not isinstance(text, str | bytes): return False

        return text.strip()[:1] in OPENERS and self.parse(text, MISSING) is not MISSING

    def looks ( self, text: object ) -> bool:
        return isinstance(text, str | bytes) and text.strip()[:1] in OPENERS

    def clone[T] ( self, value: T ) -> T:

        copied: T = orjson.loads(self.encode(value))

        return copied

    def flatten ( self, value: Mapping[str, Any], separator: str = ".", prefix: str = "" ) -> dict[str, Any]:

        flat: dict[str, Any] = {}

        for key, item in value.items():

            path = f"{prefix}{separator}{key}" if prefix else str(key)

            if isinstance(item, Mapping): flat.update(self.flatten(item, separator, path))
            else: flat[path] = item

        return flat

    def dig ( self, value: object, path: str, default: object = None, separator: str = "." ) -> Any:

        current: object = value

        for part in path.split(separator):

            if isinstance(current, Mapping) and part in current: current = current[part]
            elif isinstance(current, list) and part.lstrip("-").isdigit() and -len(current) <= int(part) < len(current):
                current = current[int(part)]
            else: return default

        return current

    def fallback ( self, value: object ) -> object:

        if isinstance(value, Decimal): return str(value)
        if isinstance(value, Enum): return value.value
        if isinstance(value, set | frozenset): return sorted(value, key=str)
        if isinstance(value, bytes | bytearray): return bytes(value).decode(errors="replace")

        dump = getattr(value, "dump", None)

        if callable(dump): return dump()

        raise TypeError(type(value).__name__)

    def loose ( self, value: object ) -> object:

        try: return self.fallback(value)
        except TypeError: return str(value)
