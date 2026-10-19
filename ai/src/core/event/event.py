from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, ClassVar, Protocol, Self, override

from core.error import Code, Fault
from core.json import json

class Event:

    registry : ClassVar[dict[str, type[Event]]] = {}
    kind     : ClassVar[str] = ""

    @override
    def __init_subclass__ ( cls, **kwargs: object ) -> None:

        super().__init_subclass__(**kwargs)

        cls.kind = f"{cls.__module__}:{cls.__qualname__}"

        Event.registry[cls.kind] = cls

    def dump ( self ) -> dict[str, Any]:

        shaped: object = self
        data: Any      = asdict(shaped) if is_dataclass(shaped) and not isinstance(shaped, type) else dict(vars(self))
        plain: dict[str, Any] = json.loads(json.encode(data))

        return plain

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Self:

        return cls(**data)

    @classmethod
    def of ( cls, name: str, data: Mapping[str, Any] ) -> Event:

        kind = cls.registry.get(name)

        if kind is None: raise Fault(Code.INTERNAL, reason=f"event.{name}")

        return kind.load(data)

    @classmethod
    def kinds ( cls ) -> list[str]:

        return sorted(cls.registry)

    def channels ( self ) -> Sequence[str]:

        return ()

    def payload ( self ) -> dict[str, Any]:

        return self.dump()

    def label ( self ) -> str:

        return type(self).__name__

class Listener(Protocol):

    async def handle ( self, event: Any ) -> None: ...
