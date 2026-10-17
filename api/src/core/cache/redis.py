from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from core.exceptions import Code, Fault
from core.json import json

BATCH = 500
MILLI = 1000

class RedisStore:

    name = "redis"

    def __init__ ( self, url: str, prefix: str = "cache", wait: float = 2.0 ) -> None:

        self._prefix = prefix.strip(":")
        self._client: Redis = Redis.from_url(url, socket_connect_timeout=wait, socket_timeout=wait)

    def key ( self, key: str ) -> str:
        return f"{self._prefix}:{key}"

    async def get ( self, key: str ) -> object | None:

        raw = await self.guard(self._client.get(self.key(key)))

        return json.loads(raw) if raw else None

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        expiry = int(ttl * MILLI) if ttl else None

        await self.guard(self._client.set(self.key(key), json.encode(value), px=expiry))

    async def delete ( self, key: str ) -> bool:
        return bool(await self.guard(self._client.delete(self.key(key))))

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        pipe = self._client.pipeline(transaction=True)

        pipe.incrby(self.key(key), step)

        if ttl: pipe.pexpire(self.key(key), int(ttl * MILLI), nx=True)

        outcome = await self.guard(pipe.execute())

        return int(outcome[0])

    async def ttl ( self, key: str ) -> float | None:

        left = int(await self.guard(self._client.pttl(self.key(key))))

        return left / MILLI if left >= 0 else None

    async def clear ( self ) -> None:

        batch: list[str] = []

        async for found in self._client.scan_iter(match=f"{self._prefix}:*", count=BATCH):

            batch.append(found)

            if len(batch) >= BATCH:

                await self.guard(self._client.delete(*batch))

                batch.clear()

        if batch: await self.guard(self._client.delete(*batch))

    async def ping ( self ) -> bool:

        try: return bool(await self._client.ping())
        except RedisError: return False

    async def close ( self ) -> None:
        await self._client.aclose()

    async def guard ( self, call: Any ) -> Any:

        try: return await call
        except RedisError as error: raise Fault(Code.UNAVAILABLE, reason="cache") from error
