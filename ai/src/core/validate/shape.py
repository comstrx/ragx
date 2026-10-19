from collections.abc import Callable, Mapping
from typing import Any, ClassVar, Self

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from core.error import Code, Fault

MISSING = object()
RULES   = frozenset({"ge", "gt", "le", "lt", "min_length", "max_length", "pattern", "multiple_of", "examples"})

def field (
    default: Any = MISSING, *, alias: str | tuple[str, ...] | None = None, factory: Callable[[], Any] | None = None,
    describe: str | None = None, **rules: Any,
) -> Any:

    unknown = set(rules) - RULES

    if unknown: raise Fault(Code.INTERNAL, reason=f"validate.field.{min(unknown)}")

    names  = (alias,) if isinstance(alias, str) else alias
    chosen = AliasChoices(*names) if names else None

    if factory is not None:
        return Field(default_factory=factory, validation_alias=chosen, description=describe, **rules)

    return Field(default=... if default is MISSING else default, validation_alias=chosen, description=describe, **rules)

def errors_of ( error: ValidationError, prefix: str | None = None ) -> dict[str, list[str]]:

    found: dict[str, list[str]] = {}

    for detail in error.errors():

        parts = [str(part) for part in detail.get("loc", ())]
        name  = ".".join(parts) or prefix or "value"

        found.setdefault(name, []).append(str(detail.get("msg", "invalid")))

    return found

class Shape(BaseModel):

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True, str_max_length=4096)

    hidden: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def of ( cls, data: object ) -> Self:

        try: return cls.model_validate(data)
        except ValidationError as error: raise Fault(Code.VALIDATION, errors=errors_of(error)) from error

    @classmethod
    def from_json ( cls, text: str | bytes ) -> Self:

        try: return cls.model_validate_json(text)
        except ValidationError as error: raise Fault(Code.VALIDATION, errors=errors_of(error)) from error

    @classmethod
    def fields ( cls ) -> list[str]:

        return list(cls.model_fields)

    @classmethod
    def required ( cls ) -> list[str]:

        return [name for name, info in cls.model_fields.items() if info.is_required()]

    @classmethod
    def json_schema ( cls ) -> dict[str, Any]:

        return cls.model_json_schema()

    def dump ( self, *, exclude_none: bool = False ) -> dict[str, Any]:

        return self.model_dump(mode="json", exclude_none=exclude_none, exclude=set(type(self).hidden))

    def only ( self, *names: str ) -> dict[str, Any]:

        dumped = self.dump()

        return { name: dumped[name] for name in names if name in dumped }

    def given ( self ) -> dict[str, Any]:

        return { name: getattr(self, name) for name in self.model_fields_set }

    def with_ ( self, **changes: Any ) -> Self:

        return self.model_copy(update=changes)

    def merged ( self, changes: Mapping[str, Any] ) -> dict[str, Any]:

        return { **self.dump(), **changes }
