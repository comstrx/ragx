from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from uuid import UUID

from engine.json import json
import re

INTEGER = re.compile(r"^[+-]?\d+$")
NUMBER  = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
HEX     = re.compile(r"^[0-9a-fA-F]+$")
TRUTHS  = frozenset({"1", "true", "yes", "on", "y", "t", "0", "false", "no", "off", "n", "f"})

class Probe:

    def is_int ( self, value: object ) -> bool:

        if isinstance(value, bool): return False
        if isinstance(value, int): return True

        return isinstance(value, str) and INTEGER.match(value.strip()) is not None

    def is_float ( self, value: object ) -> bool:

        if isinstance(value, bool): return False
        if isinstance(value, float): return True

        return isinstance(value, str) and NUMBER.match(value.strip()) is not None and not self.is_int(value)

    def is_numeric ( self, value: object ) -> bool:

        if isinstance(value, bool): return False
        if isinstance(value, int | float | Decimal): return True
        if not isinstance(value, str): return False

        try: Decimal(value.strip())
        except (InvalidOperation, ValueError): return False

        return True

    def is_bool ( self, value: object ) -> bool:

        return isinstance(value, bool) or (isinstance(value, str) and value.strip().lower() in TRUTHS)

    def is_json ( self, value: object ) -> bool:

        return json.valid(value)

    def is_mapping ( self, value: object ) -> bool:

        return isinstance(value, Mapping)

    def is_listish ( self, value: object ) -> bool:

        return isinstance(value, list | tuple | set | frozenset)

    def is_uuid ( self, value: object ) -> bool:

        if isinstance(value, UUID): return True

        try: UUID(str(value))
        except (ValueError, AttributeError, TypeError): return False

        return True

    def is_hex ( self, value: object ) -> bool:

        return isinstance(value, str) and HEX.match(value) is not None

    def is_positive ( self, value: object ) -> bool:

        if not self.is_numeric(value): return False

        return Decimal(str(value).strip()) > 0

    def is_negative ( self, value: object ) -> bool:

        if not self.is_numeric(value): return False

        return Decimal(str(value).strip()) < 0

    def is_blank ( self, value: object ) -> bool:

        return value is None or (isinstance(value, str) and value.strip() == "")

    def kind ( self, value: object ) -> str:

        if value is None: return "none"
        if isinstance(value, bool): return "bool"
        if isinstance(value, int): return "int"
        if isinstance(value, float | Decimal): return "float"
        if isinstance(value, Mapping): return "dict"
        if self.is_listish(value): return "list"
        if isinstance(value, bytes | bytearray): return "bytes"
        if isinstance(value, str):

            if self.is_int(value): return "int"
            if self.is_float(value): return "float"
            if self.is_bool(value): return "bool"
            if self.is_uuid(value): return "uuid"
            if json.looks(value) and json.valid(value): return "json"

            return "str"

        return type(value).__name__
