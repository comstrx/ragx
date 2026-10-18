from collections.abc import Awaitable, Callable
from typing import Any, cast

from .store import Store

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
