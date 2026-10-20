from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from core.error import Code, Fault
from core.log import log
from core.thread import thread
from .lock import Lock
from .store import MemoryStore, Store

type Loader[T] = Callable[[], Awaitable[T]]

class Tagged:

    def __init__ ( self, store: Store, names: tuple[str, ...] ) -> None:

        self._store = store
        self._names = tuple(sorted(set(names)))

    def names ( self ) -> tuple[str, ...]:

        return self._names

    async def version ( self ) -> str:

        found = await self._store.many(f"tag:{name}" for name in self._names)

        return ".".join(str(found.get(f"tag:{name}") or 0) for name in self._names)

    async def key ( self, key: str ) -> str:

        return f"tagged:{'+'.join(self._names)}:{await self.version()}:{key}"

    async def get ( self, key: str, default: object = None ) -> Any:

        value = await self._store.get(await self.key(key))

        return default if value is None else value

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        await self._store.set(await self.key(key), value, ttl)

    async def add ( self, key: str, value: object, ttl: float | None = None ) -> bool:

        return await self._store.add(await self.key(key), value, ttl)

    async def has ( self, key: str ) -> bool:

        return await self._store.get(await self.key(key)) is not None

    async def forget ( self, key: str ) -> bool:

        return await self._store.delete(await self.key(key))

    async def pull ( self, key: str, default: object = None ) -> Any:

        scoped = await self.key(key)
        value  = await self._store.get(scoped)

        await self._store.delete(scoped)

        return default if value is None else value

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        return await self._store.increment(await self.key(key), step, ttl)

    async def remember[T] ( self, key: str, ttl: float | None, load: Loader[T] ) -> T:

        scoped = await self.key(key)
        found  = await self._store.get(scoped)

        if found is not None: return cast("T", found)

        value = await load()

        await self._store.set(scoped, value, ttl)

        return value

    async def flush ( self ) -> int:

        for name in self._names: await self._store.increment(f"tag:{name}")

        return len(self._names)

@dataclass(frozen=True, slots=True)
class Hit:

    allowed   : bool
    remaining : int
    reset     : float

class Cache:

    def __init__ ( self, store: Store | None = None ) -> None:

        self._store: Store = store or MemoryStore()
        self._local  = MemoryStore()
        self._hits   = 0
        self._misses = 0
        self._shed   = 0

    def use ( self, store: Store ) -> None:

        self._store = store

    def store ( self ) -> Store:

        return self._store

    def name ( self ) -> str:

        return self._store.name

    async def get ( self, key: str, default: object = None ) -> Any:

        value = await self._store.get(key)

        self.count(value is not None)

        return default if value is None else value

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        await self._store.set(key, value, ttl)

    async def add ( self, key: str, value: object, ttl: float | None = None ) -> bool:

        return await self._store.add(key, value, ttl)

    async def forever ( self, key: str, value: object ) -> None:

        await self._store.set(key, value, None)

    async def forget ( self, key: str ) -> bool:

        return await self._store.delete(key)

    async def forget_many ( self, *keys: str ) -> int:

        return sum([await self._store.delete(key) for key in keys])

    async def has ( self, key: str ) -> bool:

        return await self._store.get(key) is not None

    async def missing ( self, key: str ) -> bool:

        return not await self.has(key)

    async def pull ( self, key: str, default: object = None ) -> Any:

        value = await self._store.get(key)

        if value is not None: await self._store.delete(key)

        return default if value is None else value

    async def remember[T] ( self, key: str, ttl: float | None, load: Loader[T] ) -> T:

        found = await self._store.get(key)

        self.count(found is not None)

        if found is not None: return cast("T", found)

        value = await load()

        await self._store.set(key, value, ttl)

        return value

    async def remember_forever[T] ( self, key: str, load: Loader[T] ) -> T:

        return await self.remember(key, None, load)

    async def flexible[T] ( self, key: str, fresh: float, stale: float, load: Loader[T] ) -> T:

        found = await self._store.get(key)

        if found is None: return await self.refresh(key, fresh, stale, load)
        if await self._store.get(f"{key}:fresh") is None and await self._store.add(f"{key}:refreshing", 1, fresh):
            thread.tasks.fire(self.refresh(key, fresh, stale, load), f"cache:{key}")

        return cast("T", found)

    async def refresh[T] ( self, key: str, fresh: float, stale: float, load: Loader[T] ) -> T:

        value = await load()

        await self._store.set(key, value, stale)
        await self._store.set(f"{key}:fresh", 1, fresh)
        await self._store.delete(f"{key}:refreshing")

        return value

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        return await self._store.increment(key, step, ttl)

    async def decrement ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        return await self._store.increment(key, -step, ttl)

    async def ttl ( self, key: str ) -> float | None:

        return await self._store.ttl(key)

    async def touch ( self, key: str, ttl: float ) -> bool:

        return await self._store.touch(key, ttl)

    async def many ( self, keys: Iterable[str] ) -> dict[str, Any]:

        return await self._store.many(keys)

    async def set_many ( self, values: Mapping[str, object], ttl: float | None = None ) -> int:

        for key, value in values.items(): await self._store.set(key, value, ttl)

        return len(values)

    async def hit ( self, key: str, limit: int, window: float ) -> Hit:

        try: return await self.counted(self._store, key, limit, window)
        except Fault as fault:

            if fault.code is not Code.UNAVAILABLE: raise

            self._shed += 1

            log.warning("cache.hit.degraded", store=self._store.name, reason=fault.reason)

            return await self.counted(self._local, key, limit, window)

    async def counted ( self, store: Store, key: str, limit: int, window: float ) -> Hit:

        count = await store.increment(key, 1, window)
        reset = await store.ttl(key) or window

        return Hit(allowed=count <= limit, remaining=max(limit - count, 0), reset=reset)

    def lock ( self, name: str, ttl: float = 10.0, owner: str | None = None ) -> Lock:

        return Lock(self._store, name, ttl, owner)

    def tags ( self, *names: str ) -> Tagged:

        return Tagged(self._store, names)

    async def clear ( self ) -> int:

        return await self._store.clear()

    async def close ( self ) -> None:

        await self._store.close()

    def count ( self, found: bool ) -> None:

        if found: self._hits += 1
        else: self._misses += 1

    def stats ( self ) -> dict[str, int]:

        return { "hits": self._hits, "misses": self._misses, "shed": self._shed }

    def describe ( self ) -> dict[str, object]:

        return { "store": self._store.name, **self.stats() }
