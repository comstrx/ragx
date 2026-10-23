from collections.abc import Iterable
from typing import Any, Protocol

from engine.fast import Ttl
import asyncio

class Store(Protocol):

    @property
    def name ( self ) -> str: ...

    async def get ( self, key: str ) -> object | None: ...

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None: ...

    async def add ( self, key: str, value: object, ttl: float | None = None ) -> bool: ...

    async def delete ( self, key: str ) -> bool: ...

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int: ...

    async def ttl ( self, key: str ) -> float | None: ...

    async def touch ( self, key: str, ttl: float ) -> bool: ...

    async def many ( self, keys: Iterable[str] ) -> dict[str, object | None]: ...

    async def release ( self, key: str, owner: str ) -> bool: ...

    async def clear ( self ) -> int: ...

    async def close ( self ) -> None: ...

class MemoryStore:

    name = "memory"

    def __init__ ( self, sweep: int = 512 ) -> None:

        self._entries: Ttl[str, Any] = Ttl(sweep)
        self._lock = asyncio.Lock()

    async def get ( self, key: str ) -> object | None:

        return self._entries.get(key)

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        async with self._lock: self._entries.set(key, value, ttl)

    async def add ( self, key: str, value: object, ttl: float | None = None ) -> bool:

        async with self._lock: return self._entries.add(key, value, ttl)

    async def delete ( self, key: str ) -> bool:

        return self._entries.delete(key)

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        async with self._lock: return self._entries.increment(key, step, ttl)

    async def ttl ( self, key: str ) -> float | None:

        return self._entries.ttl(key)

    async def touch ( self, key: str, ttl: float ) -> bool:

        return self._entries.touch(key, ttl)

    async def many ( self, keys: Iterable[str] ) -> dict[str, object | None]:

        return { key: self._entries.get(key) for key in keys }

    async def release ( self, key: str, owner: str ) -> bool:

        async with self._lock:

            if self._entries.get(key) != owner: return False

            return self._entries.delete(key)

    async def clear ( self ) -> int:

        count = len(self._entries)

        self._entries.clear()

        return count

    async def close ( self ) -> None:

        return None

    def size ( self ) -> int:

        return len(self._entries)

    def keys ( self ) -> list[str]:

        return self._entries.keys()
