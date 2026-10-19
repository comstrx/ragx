from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Any
from uuid import UUID

from core.json import json
import builtins

TRUTHS = frozenset({"1", "true", "yes", "on", "y", "t"})
FALSES = frozenset({"0", "false", "no", "off", "n", "f", ""})

class Cast:

    def truths ( self ) -> frozenset[str]:

        return TRUTHS

    def string ( self, value: object ) -> str | None:

        if value is None or isinstance(value, bool): return None if value is None else str(value).lower()
        if isinstance(value, bytes): value = value.decode(errors="replace")

        text = str(value).strip()

        return text or None

    def text ( self, value: object ) -> str:

        return self.string(value) or ""

    def bool ( self, value: object ) -> builtins.bool:

        if isinstance(value, bool): return value
        if isinstance(value, int | float): return value != 0
        if value is None: return False

        text = self.text(value).lower()

        if text in TRUTHS: return True
        if text in FALSES: return False

        return bool(text)

    def integer ( self, value: object, default: int = 0 ) -> int:

        if isinstance(value, bool): return int(value)
        if isinstance(value, int): return value

        try: return int(Decimal(self.text(value)))
        except (InvalidOperation, ValueError): return default

    def float ( self, value: object, default: builtins.float = 0.0, digits: int | None = None ) -> builtins.float:

        try:

            if isinstance(value, int | float) and not isinstance(value, bool): number = float(value)
            else: number = float(self.text(value))

        except ValueError: return default

        return round(number, digits) if digits is not None else number

    def decimal ( self, value: object, places: int = 2 ) -> Decimal:

        try: number = Decimal(str(value if isinstance(value, int | float) else self.text(value)))
        except InvalidOperation: number = Decimal(0)

        return number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)

    def positive ( self, value: object ) -> builtins.float:

        return max(self.float(value), 0.0)

    def list ( self, value: object ) -> builtins.list[Any]:

        if value is None: return []
        if isinstance(value, list): return value
        if isinstance(value, tuple | set | frozenset): return list(value)
        if isinstance(value, str):

            parsed = self.parse(value)

            if isinstance(parsed, list): return parsed

            return [part.strip() for part in value.split(",") if part.strip()]

        return [value]

    def dict ( self, value: object ) -> builtins.dict[str, Any]:

        if isinstance(value, Mapping): return { str(key): item for key, item in value.items() }
        if isinstance(value, str):

            parsed = self.parse(value)

            return parsed if isinstance(parsed, dict) else {}

        return {}

    def enum[E: Enum] ( self, value: object, kind: type[E], default: E | None = None ) -> E | None:

        if isinstance(value, kind): return value

        wanted = self.text(value).lower().replace("-", "_").replace(" ", "_")

        for case in kind:

            if wanted in (str(case.value).lower(), case.name.lower()): return case

        return default

    def uuid ( self, value: object ) -> UUID | None:

        if isinstance(value, UUID): return value

        try: return UUID(self.text(value))
        except ValueError: return None

    def choice[T] ( self, value: object, choices: Sequence[T], default: T | None = None ) -> T | None:

        exact = next((choice for choice in choices if choice == value), None)
        text  = self.text(value).lower()

        return exact if exact is not None else next((item for item in choices if str(item).lower() == text), default)

    def amount ( self, value: object, places: int = 2 ) -> Decimal:

        if isinstance(value, int | float | Decimal): return self.decimal(value, places)

        text  = "".join(char for char in self.text(value) if char.isdigit() or char in ".,-")
        comma = text.rfind(",")
        dot   = text.rfind(".")

        if comma > dot and len(text) - comma - 1 in (1, 2): text = text.replace(".", "").replace(",", ".")
        else: text = text.replace(",", "")

        return self.decimal(text or "0", places)

    def parse ( self, value: object ) -> object:

        if not isinstance(value, str | bytes): return value

        text = value.strip()

        if not json.looks(text): return value

        return json.parse(text, value)

    def auto ( self, value: object ) -> object:

        if not isinstance(value, str): return value

        text = value.strip()

        if text.lower() in TRUTHS or text.lower() in FALSES - {""}: return self.bool(text)
        if text.lstrip("-").isdigit(): return int(text)
        if json.looks(text): return json.parse(text, text)

        try: return float(text) if "." in text or "e" in text.lower() else text
        except ValueError: return text

    def empty ( self, value: object ) -> builtins.bool:

        if value is None or value is False: return True
        if isinstance(value, str): return value.strip() == ""
        if isinstance(value, Mapping | list | tuple | set | frozenset): return len(value) == 0

        return False

    def incoming ( self, data: Mapping[str, Any], key: str, default: object = None ) -> object:

        current: object = data

        for part in key.split("."):

            if not isinstance(current, Mapping) or part not in current: return default

            current = current[part]

        return self.parse(current)
