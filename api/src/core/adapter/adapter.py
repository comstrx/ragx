from collections.abc import Iterable
from typing import Any, ClassVar

from core.error import Code, Fault
from core.log import log

class Adapter:

    family       : ClassVar[str] = "adapter"
    capabilities : ClassVar[frozenset[str]] = frozenset()
    name         : str = "adapter"

    def abilities ( self ) -> frozenset[str]:

        return type(self).capabilities

    def supports ( self, *capabilities: str ) -> bool:

        return all(capability in self.abilities() for capability in capabilities)

    def require ( self, capability: str ) -> None:

        if capability not in self.abilities(): raise self.unsupported(capability)

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

        return { "family": type(self).family, "name": self.name, "capabilities": sorted(self.abilities()) }

def matrix ( adapters: Iterable[Adapter] ) -> dict[str, list[str]]:

    return { adapter.name: sorted(adapter.abilities()) for adapter in adapters }

class Manager[A: Adapter]:

    def __init__ ( self, family: str ) -> None:

        self._family  = family
        self._known: dict[str, A] = {}
        self._default: str | None = None

    def family ( self ) -> str:

        return self._family

    def register ( self, adapter: A, default: bool = False ) -> A:

        self._known[adapter.name] = adapter

        if default or self._default is None: self._default = adapter.name

        return adapter

    def use ( self, name: str | None = None ) -> A:

        chosen = name or self._default
        found  = self._known.get(chosen or "")

        if found is None: raise Fault(Code.INTERNAL, reason=f"{self._family}.{chosen or 'default'}.missing")

        return found

    def default ( self, name: str | None = None ) -> str | None:

        if name is not None:

            self.use(name)

            self._default = name

        return self._default

    def names ( self ) -> list[str]:

        return sorted(self._known)

    def has ( self, name: str ) -> bool:

        return name in self._known

    def ready ( self ) -> bool:

        return bool(self._known)

    def supports ( self, capability: str, name: str | None = None ) -> bool:

        return self.has(name or self._default or "") and self.use(name).supports(capability)

    def which ( self, capability: str ) -> list[str]:

        return sorted(name for name, adapter in self._known.items() if adapter.supports(capability))

    def forget ( self, name: str ) -> bool:

        found = self._known.pop(name, None) is not None

        if self._default == name: self._default = next(iter(sorted(self._known)), None)

        return found

    def clear ( self ) -> int:

        count = len(self._known)

        self._known.clear()

        self._default = None

        return count

    async def close ( self ) -> int:

        closed = 0

        for adapter in list(self._known.values()):

            try:

                await adapter.close()

                closed += 1

            except Fault as fault:
                log.warning(f"{self._family}.close_failed", provider=adapter.name, reason=fault.reason)

        return closed

    def describe ( self ) -> dict[str, Any]:

        return {
            "family"       : self._family,
            "default"      : self._default,
            "providers"    : self.names(),
            "capabilities" : matrix(self._known.values()),
        }
