from collections.abc import Iterator
from typing import Self, override

from .fault import Code, Errors, Fault

class Bag:

    __slots__ = ("_errors",)

    def __init__ ( self, errors: Errors | None = None ) -> None:

        self._errors: dict[str, list[str]] = {}

        if errors: self.merge(errors)

    def add ( self, field: str, *messages: str ) -> Self:

        kept = self._errors.setdefault(field, [])

        kept.extend(message for message in messages if message not in kept)

        return self

    def put ( self, field: str, *messages: str ) -> Self:

        self._errors[field] = list(dict.fromkeys(messages))

        return self

    def merge ( self, errors: Errors | Bag, prefix: str = "" ) -> Self:

        source = errors.dump() if isinstance(errors, Bag) else errors

        for field, messages in source.items(): self.add(f"{prefix}.{field}" if prefix else field, *messages)

        return self

    def has ( self, *fields: str ) -> bool:

        return all(self._errors.get(field) for field in fields) if fields else bool(self._errors)

    def has_any ( self, *fields: str ) -> bool:

        return any(self._errors.get(field) for field in fields)

    def first ( self, field: str | None = None ) -> str | None:

        if field is not None: return next(iter(self._errors.get(field, ())), None)

        return next((messages[0] for messages in self._errors.values() if messages), None)

    def get ( self, field: str ) -> list[str]:

        return list(self._errors.get(field, ()))

    def matching ( self, prefix: str ) -> dict[str, list[str]]:

        start = f"{prefix}."

        return { field: list(messages) for field, messages in self._errors.items() if field.startswith(start) }

    def all ( self ) -> list[str]:

        return [message for messages in self._errors.values() for message in messages]

    def keys ( self ) -> list[str]:

        return list(self._errors)

    def count ( self ) -> int:

        return sum(len(messages) for messages in self._errors.values())

    def empty ( self ) -> bool:

        return not self._errors

    def forget ( self, field: str ) -> bool:

        return self._errors.pop(field, None) is not None

    def clear ( self ) -> int:

        count = self.count()

        self._errors.clear()

        return count

    def dump ( self ) -> dict[str, list[str]]:

        return { field: list(messages) for field, messages in self._errors.items() }

    def fault ( self, reason: str | None = None, code: Code = Code.VALIDATION ) -> Fault:

        return Fault(code, reason=reason or self.reason(), errors=self.dump())

    def reason ( self ) -> str | None:

        return next(iter(self._errors), None)

    def throw ( self, reason: str | None = None, code: Code = Code.VALIDATION ) -> None:

        if self._errors: raise self.fault(reason, code)

    def __len__ ( self ) -> int:

        return self.count()

    def __iter__ ( self ) -> Iterator[str]:

        return iter(self._errors)

    def __contains__ ( self, field: object ) -> bool:

        return isinstance(field, str) and bool(self._errors.get(field))

    @override
    def __repr__ ( self ) -> str:

        return f"Bag({self._errors!r})"
