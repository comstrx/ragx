from collections.abc import Callable, Mapping
from typing import Any, Protocol

from core.cache import cache
from .job import Job

PREFIX = "queue:unique:"

class Owner(Protocol):

    async def enqueue (
        self, handler: Callable[..., Any] | str, args: tuple[Any, ...] = (), kwargs: Mapping[str, Any] | None = None,
        queue: str | None = None, delay: float = 0.0, tries: int | None = None, backoff: float | None = None,
        unique: str | None = None,
    ) -> Job: ...

class Unique:

    def __init__ ( self ) -> None:

        self.skipped = 0

    async def claim ( self, key: str, ttl: float ) -> bool:
        return await cache.add(f"{PREFIX}{key}", 1, ttl)

    async def release ( self, key: str ) -> bool:
        return await cache.forget(f"{PREFIX}{key}")

    async def held ( self, key: str ) -> bool:
        return await cache.has(f"{PREFIX}{key}")

    async def push (
        self, owner: Owner, key: str, handler: Callable[..., Any] | str, args: tuple[Any, ...],
        kwargs: Mapping[str, Any], unique_for: float, queue: str | None, delay: float,
    ) -> Job | None:

        if not await self.claim(key, unique_for):

            self.skipped += 1

            return None

        return await owner.enqueue(handler, args, kwargs, queue=queue, delay=delay, unique=key)
