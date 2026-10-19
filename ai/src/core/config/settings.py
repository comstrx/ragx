from collections.abc import Callable
from typing import Any, ClassVar, Self

from pydantic import AliasChoices, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from core.error import Code, Fault
from core.log import masked
from core.validate import MISSING, errors_of, field as shape_field

def field (
    default: Any = MISSING, *, env: str | tuple[str, ...] | None = None, factory: Callable[[], Any] | None = None,
    **rules: Any,
) -> Any:

    return shape_field(default, alias=env, factory=factory, **rules)

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        extra="ignore", frozen=True, env_nested_delimiter="__", env_ignore_empty=True, validate_default=True,
    )

    hidden: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def load ( cls, **overrides: Any ) -> Self:

        try: return cls(**overrides)
        except ValidationError as error: raise cls.fault(error) from error

    @classmethod
    def fault ( cls, error: ValidationError ) -> Fault:

        found  = errors_of(error, "settings").items()
        errors = { cls.env_key(name.split(".")[0]): messages for name, messages in found }

        return Fault(Code.INTERNAL, "The configuration is invalid", f"config.{cls.__name__}", errors)

    @classmethod
    def env_prefix ( cls ) -> str:

        return str(cls.model_config.get("env_prefix", ""))

    @classmethod
    def env_key ( cls, name: str ) -> str:

        info  = cls.model_fields.get(name)
        alias = info.validation_alias if info is not None else None

        if isinstance(alias, AliasChoices): return str(alias.choices[0])
        if isinstance(alias, str): return alias

        return f"{cls.env_prefix()}{name}".upper()

    @classmethod
    def env_keys ( cls ) -> dict[str, str]:

        return { name: cls.env_key(name) for name in cls.model_fields }

    @classmethod
    def defaults ( cls ) -> dict[str, Any]:

        return {
            name: info.get_default(call_default_factory=True)
            for name, info in cls.model_fields.items() if not info.is_required()
        }

    def dump ( self ) -> dict[str, Any]:

        return self.model_dump(mode="json")

    def describe ( self ) -> dict[str, Any]:

        shown = { name: value for name, value in self.dump().items() if name not in type(self).hidden }

        plain: dict[str, Any] = masked(shown)

        return plain

    def with_ ( self, **changes: Any ) -> Self:

        return self.model_copy(update=changes)

    def get ( self, name: str, default: Any = None ) -> Any:

        return getattr(self, name, default) if name in type(self).model_fields else default
