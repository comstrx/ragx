from collections.abc import Iterable, Mapping
from dataclasses import asdict, fields, is_dataclass
from typing import Any

class Rows:

    def into[T] ( self, model: type[T], row: Mapping[str, object] ) -> T:

        names = self.names(model)

        return model(**{ name: value for name, value in row.items() if name in names })

    def many[T] ( self, model: type[T], rows: Iterable[Mapping[str, object]] ) -> list[T]:

        names = self.names(model)

        return [model(**{ name: value for name, value in row.items() if name in names }) for row in rows]

    def dump ( self, instance: object, skip: tuple[str, ...] = () ) -> dict[str, Any]:

        if not is_dataclass(instance) or isinstance(instance, type): raise TypeError(type(instance).__name__)

        return { name: value for name, value in asdict(instance).items() if name not in skip }

    def names ( self, model: type ) -> frozenset[str]:

        if not is_dataclass(model): raise TypeError(model.__name__)

        return frozenset(field.name for field in fields(model))
