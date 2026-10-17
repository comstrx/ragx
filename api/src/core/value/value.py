from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from core.json import json
import builtins

TRUTHS = frozenset({"1", "true", "yes", "on", "y", "t"})
FALSES = frozenset({"0", "false", "no", "off", "n", "f", ""})

class Value:

    def truths ( self ) -> frozenset[str]:
        return TRUTHS

    def string ( self, value: object ) -> str | None:

        if value is None or isinstance(value, bool): return None if value is None else str(value).lower()
        if isinstance(value, bytes): value = value.decode(errors="replace")

        text = str(value).strip()

        return text or None

    def text ( self, value: object ) -> str:
        return self.string(value) or ""

    def bool ( self, value: object ) -> bool:

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

    def float ( self, value: object, default: float = 0.0, digits: int | None = None ) -> float:

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

    def list ( self, value: object ) -> list[Any]:

        if value is None: return []
        if isinstance(value, list): return value
        if isinstance(value, tuple | set | frozenset): return list(value)
        if isinstance(value, str):

            parsed = self.parse(value)

            if isinstance(parsed, list): return parsed

            return [part.strip() for part in value.split(",") if part.strip()]

        return [value]

    def dict ( self, value: object ) -> dict[str, Any]:

        if isinstance(value, Mapping): return { str(key): item for key, item in value.items() }
        if isinstance(value, str):

            parsed = self.parse(value)

            return parsed if isinstance(parsed, dict) else {}

        return {}

    def parse ( self, value: object ) -> object:

        if not isinstance(value, str | bytes): return value

        text = value.strip()

        if not json.looks(text): return value

        return json.parse(text, value)

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
