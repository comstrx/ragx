from collections.abc import Mapping
from typing import Any
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from core.error import Code, Fault
import copy

MAX_DEPTH = 16
KEYWORDS = frozenset({
    "type", "properties", "required", "items", "enum", "additionalProperties",
    "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum", "description",
})

class Shape:

    def __init__ ( self, schema: Mapping[str, Any] ) -> None:

        self._schema = copy.deepcopy(dict(schema))
        try: Draft202012Validator.check_schema(self._schema)
        except SchemaError as error: raise Fault(Code.VALIDATION, reason="json.schema") from error
        self._check(self._schema, 0)
        self._validator = Draft202012Validator(self._schema)

    def _check ( self, schema: dict[str, Any], depth: int ) -> None:

        if depth > MAX_DEPTH or set(schema) - KEYWORDS: raise Fault(Code.VALIDATION, reason="json.schema.unsupported")
        for value in schema.get("properties", {}).values():
            if isinstance(value, dict): self._check(value, depth + 1)
        for key in ("items", "additionalProperties"):
            if isinstance(schema.get(key), dict): self._check(schema[key], depth + 1)

    def dump ( self ) -> dict[str, Any]:

        return copy.deepcopy(self._schema)

    def validate ( self, value: object ) -> None:

        error = next(self._validator.iter_errors(value), None)
        if error is not None:
            path = ".".join(map(str, error.absolute_path)) or "$"
            raise Fault(Code.VALIDATION, reason="json.schema.output", errors={path: ["Schema mismatch"]})
