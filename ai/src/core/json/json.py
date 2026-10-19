from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from pathlib import PurePath
from typing import Any

from core.error import Code, Fault
from .patch import Patch
from .walk import Walk
import orjson

type JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None
type Text = str | bytes | bytearray | memoryview

OPENERS = ("{", "[", '"', b"{", b"[", b'"')
MISSING = object()
INDENT  = orjson.OPT_INDENT_2
SORTED  = orjson.OPT_SORT_KEYS
OPTIONS = {
    (pretty, ordered): orjson.OPT_NON_STR_KEYS | (INDENT if pretty else 0) | (SORTED if ordered else 0)
    for pretty in (False, True) for ordered in (False, True)
}
SHAPES: tuple[tuple[type | tuple[type, ...], Callable[[Any], object]], ...] = (
    (Decimal, str),
    (Enum, lambda value: value.value),
    ((set, frozenset), lambda value: sorted(value, key=str)),
    ((bytes, bytearray), lambda value: bytes(value).decode(errors="replace")),
    (timedelta, lambda value: value.total_seconds()),
    (PurePath, lambda value: value.as_posix()),
)

class Json(Walk, Patch):

    def dumps ( self, value: object, pretty: bool = False, sort: bool = False, lenient: bool = False ) -> str:

        return self.encode(value, pretty, sort, lenient).decode()

    def encode ( self, value: object, pretty: bool = False, sort: bool = False, lenient: bool = False ) -> bytes:

        return orjson.dumps(value, default=self.loose if lenient else self.fallback, option=OPTIONS[pretty, sort])

    def pretty ( self, value: object ) -> str:

        return self.dumps(value, pretty=True)

    def canonical ( self, value: object ) -> bytes:

        return self.encode(value, sort=True, lenient=True)

    def loads ( self, text: Text, limit: int | None = None ) -> Any:

        if limit is not None and len(text) > limit: raise Fault(Code.BAD_REQUEST, reason="json.size")

        try: return orjson.loads(text)
        except orjson.JSONDecodeError as error: raise Fault(Code.BAD_REQUEST, reason="json") from error

    def parse ( self, text: object, default: object = None, limit: int | None = None ) -> Any:

        if not isinstance(text, str | bytes | bytearray): return default
        if limit is not None and len(text) > limit: return default

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

    def plain ( self, value: object ) -> Any:

        return orjson.loads(self.encode(value, lenient=True))

    def lines ( self, text: Text ) -> Iterator[Any]:

        raw = bytes(text).decode() if isinstance(text, bytes | bytearray | memoryview) else text

        for line in raw.splitlines():

            if line.strip(): yield self.loads(line)

    def jsonl ( self, values: Iterator[object] | list[object] ) -> bytes:

        return b"\n".join(self.encode(value) for value in values) + b"\n"

    def fallback ( self, value: object ) -> object:

        for kind, shape in SHAPES:

            if isinstance(value, kind): return shape(value)

        for name in ("dump", "model_dump"):

            shaped = getattr(value, name, None)

            if callable(shaped): return shaped()

        raise TypeError(type(value).__name__)

    def loose ( self, value: object ) -> object:

        try: return self.fallback(value)
        except TypeError: return str(value)
