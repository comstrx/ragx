from collections.abc import Iterable, Mapping
from enum import Enum

from core.database import Model
from core.date import DateTime, date
from core.rand import Uuid

class BaseResource[M: Model]:

    fields : tuple[str, ...] = ()

    def one ( self, model: M ) -> dict[str, object]:

        data = model.dump()
        kept = self.fields or tuple(data)

        return { **{ name: self.value(data[name]) for name in kept if name in data }, **self.additional(model) }

    def many ( self, models: Iterable[M] ) -> list[dict[str, object]]:
        return [self.one(model) for model in models]

    def maybe ( self, model: M | None ) -> dict[str, object] | None:
        return self.one(model) if model is not None else None

    def additional ( self, _model: M ) -> dict[str, object]:
        return {}

    def value ( self, value: object ) -> object:

        if isinstance(value, Model): value = value.dump()

        match value:
            case DateTime(): return date.iso(value)
            case Uuid():     return str(value)
            case Enum():     return value.value
            case Mapping():  return { str(key): self.value(item) for key, item in value.items() }
            case list() | tuple() | set() | frozenset(): return [self.value(item) for item in value]
            case _:          return value
