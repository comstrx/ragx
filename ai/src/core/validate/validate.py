from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, create_model
from core.error import Code, Fault
from .checked import BOOK
from .rule import Rules
from .rules import Email, Phone, Url
import functools

type Errors = dict[str, list[str]]
type Shape = Mapping[str, Any]

@functools.cache
def adapter ( kind: Any ) -> TypeAdapter[Any]:

    return TypeAdapter(kind)

class Validate:

    def __init__ ( self ) -> None:

        self.rules = BOOK
        self.build = Rules()

    def make (
        self, data: Mapping[str, Any], rules: Mapping[str, str | list[str]], messages: Mapping[str, str] | None = None,
    ) -> Errors:

        return self.rules.check(data, rules, messages)

    def validated (
        self, data: Mapping[str, Any], rules: Mapping[str, str | list[str]], messages: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:

        return self.rules.validate(data, rules, messages)

    def extend ( self, name: str, check: Any ) -> None:

        self.rules.extend(name, check)

    def check ( self, kind: Any, value: object, field: str = "value" ) -> Any:

        try: return adapter(kind).validate_python(value)
        except ValidationError as error: raise self.fault(error, field) from error

    def check_json ( self, kind: Any, text: str | bytes, field: str = "value" ) -> Any:

        try: return adapter(kind).validate_json(text)
        except ValidationError as error: raise self.fault(error, field) from error

    def model[M: BaseModel] ( self, model: type[M], data: object ) -> M:

        try: return model.model_validate(data)
        except ValidationError as error: raise self.fault(error) from error

    def schema ( self, title: str = "Shape", /, **fields: Any ) -> type[BaseModel]:

        definitions: dict[str, Any] = {
            key: (kind if isinstance(kind, tuple) else (kind, ...)) for key, kind in fields.items()
        }
        config = ConfigDict(extra="forbid", str_strip_whitespace=True)

        return create_model(title, __config__=config, **definitions)

    def shape ( self, data: object, **fields: Any ) -> dict[str, Any]:

        return self.model(self.schema(**fields), data).model_dump()

    def errors ( self, error: ValidationError, field: str | None = None ) -> Errors:

        errors: Errors = {}

        for detail in error.errors():

            parts = [str(part) for part in detail.get("loc", ())]
            name  = ".".join(parts) or field or "value"

            errors.setdefault(name, []).append(str(detail.get("msg", "invalid")))

        return errors

    def fault ( self, error: ValidationError, field: str | None = None ) -> Fault:

        return Fault(Code.VALIDATION, errors=self.errors(error, field))

    def passes ( self, kind: Any, value: object ) -> bool:

        try: adapter(kind).validate_python(value)
        except ValidationError: return False

        return True

    def failures ( self, kind: Any, value: object, field: str = "value" ) -> Errors:

        try: adapter(kind).validate_python(value)
        except ValidationError as error: return self.errors(error, field)

        return {}

    def is_email ( self, value: object ) -> bool:

        return self.passes(Email, value)

    def is_phone ( self, value: object ) -> bool:

        return self.passes(Phone, value)

    def is_url ( self, value: object ) -> bool:

        return self.passes(Url, value)

    def is_uuid ( self, value: object ) -> bool:

        if isinstance(value, UUID): return True

        try: UUID(str(value))
        except ValueError: return False

        return True

    def one_of[T] ( self, value: T, choices: Sequence[T], field: str = "value" ) -> T:

        if value in choices: return value

        raise Fault(Code.VALIDATION, errors={ field: [f"Choose one of: {', '.join(map(str, choices))}"] })

    def required ( self, data: Mapping[str, object], *names: str ) -> None:

        missing = { name: ["This field is required"] for name in names if data.get(name) in (None, "", [], {}) }

        if missing: raise Fault(Code.VALIDATION, errors=missing)

    def refuse ( self, field: str, message: str ) -> Fault:

        return Fault(Code.VALIDATION, errors={ field: [message] })

    def merge ( self, *groups: Errors ) -> Errors:

        merged: Errors = {}

        for group in groups:
            for field, messages in group.items(): merged.setdefault(field, []).extend(messages)

        return merged
