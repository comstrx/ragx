from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

from core.error import Code, Fault
from core.rand import rand
from .store import Store
import asyncio

type Work[T] = Callable[[], Awaitable[T]]

TTL   = 10.0
EVERY = 0.05

class Lock:

    def __init__ ( self, store: Store, name: str, ttl: float = TTL, owner: str | None = None ) -> None:

        self._store = store
        self._name  = name
        self._ttl   = ttl
        self._owner = owner or rand.token(16)
        self._held  = False
        self._wait  = 0.0

    def key ( self ) -> str:

        return f"lock:{self._name}"

    def owner ( self ) -> str:

        return self._owner

    def owned ( self ) -> bool:

        return self._held

    async def acquire ( self, wait: float = 0.0, every: float = EVERY ) -> bool:

        deadline = asyncio.get_running_loop().time() + max(wait, 0.0)

        while True:

            if await self._store.add(self.key(), self._owner, self._ttl):

                self._held = True

                return True

            if asyncio.get_running_loop().time() >= deadline: return False

            await asyncio.sleep(every)

    async def release ( self ) -> bool:

        if not self._held: return False

        self._held = False

        return await self._store.release(self.key(), self._owner)

    async def extend ( self, ttl: float | None = None ) -> bool:

        return self._held and await self._store.touch(self.key(), ttl or self._ttl)

    async def force_release ( self ) -> bool:

        self._held = False

        return await self._store.delete(self.key())

    async def holder ( self ) -> str | None:

        found = await self._store.get(self.key())

        return str(found) if found is not None else None

    async def get[T] ( self, work: Work[T], wait: float = 0.0 ) -> T:

        if not await self.acquire(wait): raise Fault(Code.CONFLICT, reason="lock.busy")

        try: return await work()
        finally: await self.release()

    async def block[T] ( self, wait: float, work: Work[T] ) -> T:

        return await self.get(work, wait)

    def waiting ( self, wait: float ) -> Self:

        self._wait = wait

        return self

    async def __aenter__ ( self ) -> Self:

        if not await self.acquire(self._wait): raise Fault(Code.CONFLICT, reason="lock.busy")

        return self

    async def __aexit__ (
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None,
    ) -> None:

        await self.release()
