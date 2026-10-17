from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast
import asyncio, time

type Loader[T] = Callable[[], Awaitable[T]]

@dataclass(frozen=True, slots=True)
class Hit:

    allowed   : bool
    remaining : int
    reset     : float

class Store(Protocol):

    async def get ( self, key: str ) -> object | None: ...

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None: ...

    async def delete ( self, key: str ) -> bool: ...

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int: ...

    async def ttl ( self, key: str ) -> float | None: ...

    async def clear ( self ) -> None: ...

class MemoryStore:

    sweep = 512

    def __init__ ( self ) -> None:

        self._entries: dict[str, tuple[float | None, object]] = {}
        self._lock = asyncio.Lock()

    async def get ( self, key: str ) -> object | None:

        entry = self._entries.get(key)

        if entry is None: return None
        if entry[0] is not None and entry[0] <= time.monotonic():

            self._entries.pop(key, None)

            return None

        return entry[1]

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        async with self._lock:

            if len(self._entries) >= self.sweep: self._sweep_()

            self._entries[key] = (time.monotonic() + ttl if ttl else None, value)

    async def delete ( self, key: str ) -> bool:
        return self._entries.pop(key, None) is not None

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        async with self._lock:

            entry   = self._entries.get(key)
            expired = entry is not None and entry[0] is not None and entry[0] <= time.monotonic()
            current = 0 if entry is None or expired else int(entry[1]) if isinstance(entry[1], int) else 0
            expiry  = (time.monotonic() + ttl if ttl else None) if entry is None or expired else entry[0]

            self._entries[key] = (expiry, current + step)

            return current + step

    async def ttl ( self, key: str ) -> float | None:

        entry = self._entries.get(key)

        if entry is None or entry[0] is None: return None

        return max(entry[0] - time.monotonic(), 0.0)

    async def clear ( self ) -> None:
        self._entries.clear()

    def _sweep_ ( self ) -> None:

        now = time.monotonic()

        for key in [key for key, (expiry, _) in self._entries.items() if expiry is not None and expiry <= now]:
            self._entries.pop(key, None)

class Cache:

    def __init__ ( self, store: Store | None = None ) -> None:

        self._store: Store = store or MemoryStore()

    def use ( self, store: Store ) -> None:
        self._store = store

    async def get ( self, key: str, default: object = None ) -> Any:

        value = await self._store.get(key)

        return default if value is None else value

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:
        await self._store.set(key, value, ttl)

    async def forget ( self, key: str ) -> bool:
        return await self._store.delete(key)

    async def has ( self, key: str ) -> bool:
        return await self._store.get(key) is not None

    async def remember[T] ( self, key: str, ttl: float | None, load: Loader[T] ) -> T:

        found = await self._store.get(key)

        if found is not None: return cast("T", found)

        value = await load()

        await self._store.set(key, value, ttl)

        return value

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:
        return await self._store.increment(key, step, ttl)

    async def hit ( self, key: str, limit: int, window: float ) -> Hit:

        count = await self._store.increment(key, 1, window)
        reset = await self._store.ttl(key) or window

        return Hit(allowed=count <= limit, remaining=max(limit - count, 0), reset=reset)

    async def clear ( self ) -> None:
        await self._store.clear()

    async def close ( self ) -> None:

        closer = getattr(self._store, "close", None)

        if callable(closer): await closer()
