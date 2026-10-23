from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, ClassVar, Self

from engine.error import Code, Fault
from engine.log import masked
from engine.parse import parse
from engine.validate import MISSING, errors_of, field as shape_field
from pydantic import AliasChoices, BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

def field (
    default: Any = MISSING, *, env: str | tuple[str, ...] | None = None, factory: Callable[[], Any] | None = None,
    **rules: Any,
) -> Any:

    return shape_field(default, alias=env, factory=factory, **rules)

def concealed ( value: object, data: object ) -> Any:

    if not isinstance(value, BaseModel) or not isinstance(data, dict): return data

    hidden = getattr(type(value), "hidden", ())

    return { name: concealed(getattr(value, name, None), item) for name, item in data.items() if name not in hidden }

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        extra="ignore", frozen=True, env_nested_delimiter="__", env_ignore_empty=True, validate_default=True,
    )

    hidden: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def load ( cls, **overrides: Any ) -> Self:

        try: return cls(**overrides)
        except ValidationError as error: raise cls._fault_(error) from error

    @classmethod
    def _fault_ ( cls, error: ValidationError ) -> Fault:

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

        plain: dict[str, Any] = masked(concealed(self, self.dump()))

        return plain

    def with_ ( self, **changes: Any ) -> Self:

        return self.model_copy(update=changes)

    def get ( self, name: str, default: Any = None ) -> Any:

        return getattr(self, name, default) if name in type(self).model_fields else default

class Config:

    def __init__ ( self ) -> None:

        self._models: dict[str, Settings] = {}
        self._overrides: dict[str, object] = {}

    def register[S: Settings] ( self, name: str, kind: type[S], **overrides: Any ) -> S:

        known = self._models.get(name)

        if isinstance(known, kind) and not overrides: return known

        loaded = kind.load(**overrides)

        self._models[name] = loaded

        return loaded

    def of[S: Settings] ( self, name: str, kind: type[S] ) -> S:

        known = self._models.get(name)

        if not isinstance(known, kind): raise Fault(Code.INTERNAL, reason=f"config.{name}")

        return known

    def forget ( self, name: str ) -> bool:

        return self._models.pop(name, None) is not None

    def names ( self ) -> list[str]:

        return sorted(self._models)

    def get ( self, key: str, default: Any = None ) -> Any:

        if key in self._overrides: return self._overrides[key]

        name, _, rest = key.partition(".")
        current: object = self._models.get(name)

        if current is None: return default
        if not rest: return current

        for part in rest.split("."):

            if isinstance(current, BaseModel) and part in type(current).model_fields: current = getattr(current, part)
            elif isinstance(current, Mapping) and part in current: current = current[part]
            else: return default

        return current

    def require ( self, key: str ) -> Any:

        found = self.get(key, MISSING)

        if found is MISSING: raise Fault(Code.INTERNAL, reason=f"config.{key}")

        return found

    def has ( self, key: str ) -> bool:

        return self.get(key, MISSING) is not MISSING

    def set ( self, key: str, item: object ) -> None:

        self._overrides[key] = item

    def remove ( self, key: str ) -> bool:

        return self._overrides.pop(key, MISSING) is not MISSING

    @contextmanager
    def scoped ( self, **items: object ) -> Iterator[None]:

        keys     = { name.replace("__", "."): item for name, item in items.items() }
        previous = { key: self._overrides.get(key, MISSING) for key in keys }

        self._overrides.update(keys)

        try: yield
        finally:

            for key, item in previous.items():

                if item is MISSING: self._overrides.pop(key, None)
                else: self._overrides[key] = item

    def integer ( self, key: str, default: int = 0 ) -> int:

        return parse.integer(self.get(key, default), default)

    def number ( self, key: str, default: float = 0.0 ) -> float:

        return parse.float(self.get(key, default), default)

    def flag ( self, key: str, default: bool = False ) -> bool:

        found = self.get(key, None)

        return default if found is None else parse.bool(found)

    def text ( self, key: str, default: str = "" ) -> str:

        found = self.get(key, None)

        return default if found is None else parse.text(found)

    def items ( self, key: str ) -> list[Any]:

        return parse.list(self.get(key, None))

    def duration ( self, key: str, default: float = 0.0 ) -> float:

        return parse.duration(self.get(key, default), default)

    def env_keys ( self ) -> dict[str, str]:

        models = self._models.items()

        return { f"{name}.{field}": key for name, model in models for field, key in model.env_keys().items() }

    def all ( self ) -> dict[str, Any]:

        snapshot: dict[str, Any] = { name: model.dump() for name, model in self._models.items() }

        for key, item in self._overrides.items():

            name, _, rest = key.partition(".")

            if not rest: snapshot[name] = item
            else: snapshot.setdefault(name, {})[rest] = item

        return snapshot

    def describe ( self ) -> dict[str, Any]:

        described: dict[str, Any] = {}

        for name, model in self._models.items():

            described[name] = { **model.describe(), **masked(self.overrides_of(name)) }

        return described

    def overrides_of ( self, name: str ) -> dict[str, object]:

        start = f"{name}."

        return { key.removeprefix(start): item for key, item in self._overrides.items() if key.startswith(start) }

    def clear ( self ) -> int:

        count = len(self._models)

        self._models.clear()
        self._overrides.clear()

        return count
