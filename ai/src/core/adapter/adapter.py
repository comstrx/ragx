from collections.abc import Iterable
from typing import Any, ClassVar

from core.error import Code, Fault

class Adapter:

    family       : ClassVar[str] = "adapter"
    capabilities : ClassVar[frozenset[str]] = frozenset()
    name         : str = "adapter"

    def supports ( self, *capabilities: str ) -> bool:

        return all(capability in type(self).capabilities for capability in capabilities)

    def require ( self, capability: str ) -> None:

        if capability not in type(self).capabilities: raise self.unsupported(capability)

    def unsupported ( self, capability: str ) -> Fault:

        return Fault(Code.INTERNAL, reason=f"{type(self).family}.{self.name}.unsupported.{capability}")

    def reason ( self, action: str ) -> str:

        return f"{type(self).family}.{self.name}.{action}"

    def fault ( self, code: Code, action: str, message: str | None = None, retry: float | None = None ) -> Fault:

        return Fault(code, message, self.reason(action), retry_after=retry)

    def missing ( self, *pairs: tuple[str, object] ) -> None:

        absent = [name for name, value in pairs if value in (None, "", [], {})]

        if absent: raise Fault(Code.INTERNAL, reason=self.reason(f"config.{absent[0]}"))

    async def close ( self ) -> None:

        return None

    def describe ( self ) -> dict[str, Any]:

        return { "family": type(self).family, "name": self.name, "capabilities": sorted(type(self).capabilities) }

def matrix ( adapters: Iterable[Adapter] ) -> dict[str, list[str]]:

    return { adapter.name: sorted(type(adapter).capabilities) for adapter in adapters }
