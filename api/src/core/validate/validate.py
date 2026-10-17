from collections.abc import Sequence
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, StringConstraints, TypeAdapter, ValidationError
from core.exceptions import Code, Fault
import functools

type Errors = dict[str, list[str]]

EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE = r"^\+[1-9]\d{6,14}$"
NAME  = r"^[\w .'-]+$"
SLUG  = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
UUIDS = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

Email      = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=254, pattern=EMAIL),
]
Phone      = Annotated[str, StringConstraints(strip_whitespace=True, pattern=PHONE)]
Password   = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Name       = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120, pattern=NAME)]
Slug       = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=120, pattern=SLUG),
]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, pattern=UUIDS)]

@functools.cache
def adapter ( kind: Any ) -> TypeAdapter[Any]:
    return TypeAdapter(kind)

class Validate:

    def check ( self, kind: Any, value: object, field: str = "value" ) -> Any:

        try: return adapter(kind).validate_python(value)
        except ValidationError as error: raise self.fault(error, field) from error

    def model[M: BaseModel] ( self, model: type[M], data: object ) -> M:

        try: return model.model_validate(data)
        except ValidationError as error: raise self.fault(error) from error

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

    def is_email ( self, value: object ) -> bool:
        return self.passes(Email, value)

    def is_phone ( self, value: object ) -> bool:
        return self.passes(Phone, value)

    def is_uuid ( self, value: object ) -> bool:

        if isinstance(value, UUID): return True

        try: UUID(str(value))
        except ValueError: return False

        return True

    def one_of[T] ( self, value: T, choices: Sequence[T], field: str = "value" ) -> T:

        if value in choices: return value

        raise Fault(Code.VALIDATION, errors={ field: [f"Choose one of: {', '.join(map(str, choices))}"] })
