from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from core.date import date

@dataclass(frozen=True, slots=True)
class Claims:

    subject : str
    kind    : str
    id      : str
    issued  : datetime
    expires : datetime
    extra   : Mapping[str, object] = field(default_factory=dict)

    def remaining ( self ) -> float:

        return max((self.expires - date.now()).total_seconds(), 0.0)

    def alive ( self ) -> bool:

        return self.expires > date.now()

    def age ( self ) -> float:

        return max((date.now() - self.issued).total_seconds(), 0.0)

    def get ( self, name: str, default: Any = None ) -> Any:

        return self.extra.get(name, default)

    def is_kind ( self, *kinds: str ) -> bool:

        return self.kind in kinds

    def dump ( self ) -> dict[str, Any]:

        return {
            "subject": self.subject, "kind": self.kind, "id": self.id, "issued": date.iso(self.issued),
            "expires": date.iso(self.expires), "extra": dict(self.extra),
        }

class Adapter(Protocol):

    def issue ( self, claims: Claims ) -> str: ...

    def verify ( self, text: str ) -> Claims: ...

    def peek ( self, text: str ) -> Claims: ...
