from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from core.error import Code, Fault

MISSING = object()

class Slots:

    def __init__ ( self ) -> None:

        self._slots: dict[str, ContextVar[Any]] = {}
        self._hidden: set[str] = set()

    def slot ( self, name: str ) -> ContextVar[Any]:

        found = self._slots.get(name)

        if found is None: found = self._slots[name] = ContextVar(name, default=MISSING)

        return found

    def get ( self, name: str, default: Any = None ) -> Any:

        found = self.slot(name).get()

        return default if found is MISSING else found

    def require ( self, name: str ) -> Any:

        found = self.slot(name).get()

        if found is MISSING: raise Fault(Code.INTERNAL, reason=f"context.{name}")

        return found

    def has ( self, name: str ) -> bool:

        return self.slot(name).get() is not MISSING

    def set ( self, name: str, value: object ) -> Token[Any]:

        return self.slot(name).set(value)

    def put ( self, **values: object ) -> None:

        for name, value in values.items(): self.slot(name).set(value)

    def push ( self, name: str, *values: object ) -> list[Any]:

        current = self.get(name)
        stacked = [*(current if isinstance(current, list) else ()), *values]

        self.slot(name).set(stacked)

        return stacked

    def increment ( self, name: str, step: int = 1 ) -> int:

        current = self.get(name, 0)
        total   = (current if isinstance(current, int) else 0) + step

        self.slot(name).set(total)

        return total

    def reset ( self, name: str, token: Token[Any] ) -> None:

        self.slot(name).reset(token)

    def clear ( self, name: str ) -> None:

        self.slot(name).set(MISSING)

    def forget ( self, *names: str ) -> int:

        cleared = [name for name in names if self.has(name)]

        for name in cleared: self.clear(name)

        return len(cleared)

    def hide ( self, *names: str ) -> None:

        self._hidden.update(names)

    def hidden ( self, name: str ) -> bool:

        return name in self._hidden

    def names ( self ) -> list[str]:

        return sorted(name for name in self._slots if self.has(name))

    def snapshot ( self, hidden: bool = False ) -> dict[str, Any]:

        found = { name: var.get() for name, var in self._slots.items() }

        return {
            name: value for name, value in found.items()
            if value is not MISSING and (hidden or name not in self._hidden)
        }

    @contextmanager
    def bind ( self, **values: object ) -> Iterator[None]:

        tokens = [(name, self.set(name, value)) for name, value in values.items()]

        try: yield
        finally:

            for name, token in reversed(tokens): self.reset(name, token)

    @contextmanager
    def restored ( self, values: Mapping[str, object] ) -> Iterator[None]:

        with self.bind(**dict(values)): yield
