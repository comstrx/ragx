from collections.abc import Callable, Mapping
from typing import Annotated, Any, ClassVar, Self

from core.error import Code, Fault
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError
from .rule import Rule

MISSING = object()
RULES   = frozenset({"ge", "gt", "le", "lt", "min_length", "max_length", "pattern", "multiple_of", "examples"})
PHONE    = r"^\+[1-9]\d{6,14}$"
NAME     = r"^[\w .'-]+$"
SLUG     = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
USERNAME = r"^[a-z0-9](?:[a-z0-9._-]{0,30}[a-z0-9])?$"
LOCALE   = r"^[a-z]{2,3}(?:[-_][A-Za-z]{2,4})?$"
CURRENCY = r"^[A-Z]{3}$"
COUNTRY  = r"^[A-Z]{2}$"
COLOR    = r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
LABEL    = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
HOSTNAME = rf"^(?=.{{1,253}}$)(?:{LABEL}\.)*{LABEL}$"
TIMEZONE = r"^[A-Za-z_]+(?:/[A-Za-z_+-]+){0,2}$"
HEX      = r"^[0-9a-fA-F]+$"
DIGITS   = r"^\d+$"
TEXT     = Rule().string().trim()

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

Email       = Annotated[str, TEXT.lower().email().between(3, 254)]
Phone       = Annotated[str, TEXT.latin_digits().regex(PHONE)]
Password    = Annotated[str, Rule().string().between(8, 128)]
Name        = Annotated[str, TEXT.squish().regex(NAME).between(1, 120)]
Slug        = Annotated[str, TEXT.lower().regex(SLUG).between(1, 120)]
Identifier  = Annotated[str, TEXT.lower().uuid()]
Url         = Annotated[str, TEXT.url().between(8, 2048)]
Username    = Annotated[str, TEXT.lower().regex(USERNAME).between(2, 32)]
Locale      = Annotated[str, TEXT.regex(LOCALE)]
Currency    = Annotated[str, TEXT.upper().regex(CURRENCY)]
Country     = Annotated[str, TEXT.upper().regex(COUNTRY)]
Color       = Annotated[str, TEXT.regex(COLOR)]
Hostname    = Annotated[str, TEXT.lower().regex(HOSTNAME).between(1, 253)]
Timezone    = Annotated[str, TEXT.regex(TIMEZONE)]
Hex         = Annotated[str, TEXT.regex(HEX)]
Digits      = Annotated[str, TEXT.latin_digits().regex(DIGITS)]
Title       = Annotated[str, TEXT.squish().between(1, 200)]
Text        = Annotated[str, TEXT.between(1, 10_000)]
Port        = Annotated[int, Rule().integer().between(1, 65535)]
Positive    = Annotated[int, Rule().integer().min(1)]
NonNegative = Annotated[int, Rule().integer().min(0)]
Percent     = Annotated[float, Rule().numeric().between(0, 100)]
Ratio       = Annotated[float, Rule().numeric().between(0, 1)]
Page        = Annotated[int, Rule().integer().min(1)]
Limit       = Annotated[int, Rule().integer().between(1, 200)]
