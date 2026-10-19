from collections.abc import Callable, Mapping
from typing import Any, cast

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import PydanticCustomError, core_schema
from core.error import Code, Fault
from core.string import string
from .rulebook import Rulebook

type Shift = Callable[[Any], Any]
type Custom = tuple[Callable[[Any], bool], str]

BOOK   = Rulebook()
KIND   = "rule"
SHIFTS: dict[str, Shift] = {
    "trim"   : lambda value: value.strip() if isinstance(value, str) else value,
    "lower"  : lambda value: value.lower() if isinstance(value, str) else value,
    "upper"  : lambda value: value.upper() if isinstance(value, str) else value,
    "squish" : lambda value: string.squish(value) if isinstance(value, str) else value,
    "digits" : lambda value: string.latin_digits(value) if isinstance(value, str) else value,
    "arabic" : lambda value: string.arabic(value) if isinstance(value, str) else value,
}
FLAGS  = { "trim": "strip_whitespace", "lower": "to_lower", "upper": "to_upper" }
SHAPES = {
    "email" : r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    "uuid"  : r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
}
KINDS  = { "str": "string", "int": "integer", "float": "numeric" }
HINTS  = {
    "email": { "format": "email" }, "url": { "format": "uri" }, "uuid": { "format": "uuid" },
    "ip": { "format": "ip" }, "date": { "format": "date-time" },
}

def split ( step: str ) -> tuple[str, list[str], str]:

    name, _, raw = step.partition(":")

    return name, raw.split(",") if raw else [], raw

def numbers ( args: list[str] ) -> list[float]:

    return [float(arg) for arg in args if arg.replace(".", "", 1).lstrip("-").isdigit()]

class Checked:

    __slots__ = ("_custom", "_shifts", "_steps")

    def __init__ (
        self, steps: tuple[str, ...] = (), shifts: tuple[str, ...] = (), custom: tuple[Custom, ...] = (),
    ) -> None:

        self._steps  = steps
        self._shifts = shifts
        self._custom = custom

    def spec ( self ) -> list[str]:

        return list(self._steps)

    def text ( self ) -> str:

        return "|".join(self._steps)

    def prepare ( self, value: Any, shifts: tuple[str, ...] | None = None ) -> Any:

        for name in self._shifts if shifts is None else shifts: value = SHIFTS[name](value)

        return value

    def errors (
        self, value: Any, field: str = "value", data: Mapping[str, Any] | None = None, present: bool = False,
    ) -> list[str]:

        ready = self.prepare(value)

        return self.judge(ready, list(self._steps), field, data, present)

    def judge (
        self, ready: Any, steps: list[str], field: str = "value", data: Mapping[str, Any] | None = None,
        present: bool = False,
    ) -> list[str]:

        spec  = ["required", *steps] if present and ready is not None else steps
        found = BOOK.field_errors(field, spec, { **(data or {}), field: ready }) if spec else []

        if found or ready is None: return found

        return [message for test, message in self._custom if not test(ready)]

    def check ( self, value: Any, field: str = "value", data: Mapping[str, Any] | None = None ) -> Any:

        found = self.errors(value, field, data)

        if found: raise Fault(Code.VALIDATION, reason=field, errors={ field: found })

        return self.prepare(value)

    def passes ( self, value: Any ) -> bool:

        return not self.errors(value)

    def native ( self, base: dict[str, Any] ) -> tuple[list[str], tuple[str, ...]]:

        kind      = KINDS.get(str(base.get("type")))
        text      = kind == "string"
        before    = tuple(name for name in self._shifts if not (text and name in FLAGS))
        residual: list[str] = []
        patterns: list[str] = []

        for name in self._shifts:

            if text and name in FLAGS: base[FLAGS[name]] = True

        for step in self._steps:

            name, args, raw = split(step)
            found = numbers(args)

            if name == kind: continue
            if text and name in SHAPES: patterns.append(SHAPES[name])
            elif text and name == "regex": patterns.append(raw)
            elif name in ("min", "max", "between") and kind and found: self.bound(base, name, found, text)
            else: residual.append(step)

        if len(patterns) == 1: base["pattern"] = patterns[0]
        else: residual.extend(f"regex:{pattern}" for pattern in patterns)

        return residual, before

    def bound ( self, base: dict[str, Any], name: str, found: list[float], text: bool ) -> None:

        low, high = ("min_length", "max_length") if text else ("ge", "le")
        whole     = text or base.get("type") == "int"
        values    = [int(number) if whole else number for number in found]

        if name in ("min", "between"): base[low] = values[0]
        if name == "max": base[high] = values[0]
        if name == "between" and len(values) > 1: base[high] = values[1]

    def __get_pydantic_core_schema__ ( self, source: Any, handler: GetCoreSchemaHandler ) -> core_schema.CoreSchema:

        base: dict[str, Any]           = dict(handler(source))
        residual, before               = self.native(base)
        schema: core_schema.CoreSchema = cast("core_schema.CoreSchema", base)

        if before:

            def shifted ( value: Any ) -> Any:

                return self.prepare(value, before)

            schema = core_schema.no_info_before_validator_function(shifted, schema)

        if not (residual or self._custom): return schema

        def validated ( value: Any ) -> Any:

            found = self.judge(value, residual, present=True)

            if found: raise PydanticCustomError(KIND, found[0])

            return value

        return core_schema.no_info_after_validator_function(validated, schema)

    def __get_pydantic_json_schema__ ( self, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler ) -> Any:

        shown = dict(handler(schema))

        for step in self._steps:

            name, args, _ = split(step)

            shown.update(HINTS.get(name, {}))

            if name == "in": shown["enum"] = args

        return shown
