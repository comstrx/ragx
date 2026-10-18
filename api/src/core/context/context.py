from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any
from uuid import uuid7

MISSING = object()

class Context:

    def __init__ ( self ) -> None:

        self._slots: dict[str, ContextVar[Any]] = {}
        self._request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

    def request_id ( self ) -> str | None:
        return self._request_id.get()

    def start ( self, request_id: str | None = None ) -> Token[str | None]:
        return self._request_id.set(request_id or str(uuid7()))

    def finish ( self, token: Token[str | None] ) -> None:
        self._request_id.reset(token)

    def slot ( self, name: str ) -> ContextVar[Any]:

        found = self._slots.get(name)

        if found is None: found = self._slots[name] = ContextVar(name, default=MISSING)

        return found

    def get ( self, name: str, default: Any = None ) -> Any:

        found = self.slot(name).get()

        return default if found is MISSING else found

    def require ( self, name: str ) -> Any:

        found = self.slot(name).get()

        if found is MISSING: raise LookupError(name)

        return found

    def has ( self, name: str ) -> bool:
        return self.slot(name).get() is not MISSING

    def set ( self, name: str, value: object ) -> Token[Any]:
        return self.slot(name).set(value)

    def reset ( self, name: str, token: Token[Any] ) -> None:
        self.slot(name).reset(token)

    def clear ( self, name: str ) -> None:
        self.slot(name).set(MISSING)

    def names ( self ) -> list[str]:
        return sorted(self._slots)

    def snapshot ( self ) -> dict[str, Any]:

        found = { name: var.get() for name, var in self._slots.items() }

        return { name: value for name, value in found.items() if value is not MISSING }

    @contextmanager
    def bind ( self, **values: object ) -> Iterator[None]:

        tokens = [(name, self.set(name, value)) for name, value in values.items()]

        try: yield
        finally:
            for name, token in reversed(tokens): self.reset(name, token)
