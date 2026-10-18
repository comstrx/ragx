from dataclasses import dataclass, field
from typing import Any

from core.error import Code, Fault
from core.json import json as codec

SUCCESS = range(200, 300)
CLIENT  = 400

@dataclass(frozen=True, slots=True)
class Reply:

    status  : int
    headers : dict[str, str]
    body    : bytes
    url     : str
    ms      : float = field(default=0.0)

    def ok ( self ) -> bool:
        return self.status in SUCCESS

    def failed ( self ) -> bool:
        return self.status >= CLIENT

    def text ( self ) -> str:
        return self.body.decode(errors="replace")

    def json ( self ) -> Any:
        return codec.loads(self.body) if self.body else None

    def data ( self, key: str = "data", default: Any = None ) -> Any:

        parsed = self.json()

        return parsed.get(key, default) if isinstance(parsed, dict) else default

    def header ( self, name: str, default: str = "" ) -> str:
        return self.headers.get(name.lower(), self.headers.get(name, default))

    def content_type ( self ) -> str:
        return self.header("content-type").split(";")[0].strip().lower()

    def is_json ( self ) -> bool:
        return self.content_type().endswith("json")

    def raise_for_status ( self, reason: str = "upstream" ) -> Reply:

        if self.ok(): return self

        raise Fault(Code.of(self.status) if self.status >= CLIENT else Code.UNAVAILABLE, reason=reason)

    def expect ( self, status: int, reason: str = "upstream" ) -> Reply:

        if self.status == status: return self

        raise Fault(Code.of(self.status) if self.status >= CLIENT else Code.UNAVAILABLE, reason=reason)

    def dump ( self ) -> dict[str, Any]:
        return { "status": self.status, "url": self.url, "ms": self.ms, "bytes": len(self.body) }

@dataclass(frozen=True, slots=True)
class Sse:

    data  : str
    event : str = "message"
    id    : str | None = None
    retry : int | None = None

    def json ( self ) -> Any:
        return codec.parse(self.data)
