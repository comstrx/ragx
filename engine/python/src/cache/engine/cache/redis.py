from collections.abc import Iterable
from typing import Any

from engine.error import Code, Fault
from engine.json import json
from redis.asyncio import Redis
from redis.exceptions import RedisError

BATCH   = 500
MILLI   = 1000
RELEASE = 'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) else return 0 end'
COUNT   = (
    'local value = redis.call("incrby", KEYS[1], ARGV[1]) '
    'if tonumber(ARGV[2]) > 0 then redis.call("pexpire", KEYS[1], ARGV[2], "NX") end return value'
)

class RedisStore:

    name = "redis"

    def __init__ ( self, url: str, prefix: str = "cache", wait: float = 2.0 ) -> None:

        self._prefix = prefix.strip(":")
        self._client: Redis = Redis.from_url(url, socket_connect_timeout=wait, socket_timeout=wait)

    def key ( self, key: str ) -> str:

        return f"{self._prefix}:{key}"

    def _client_ ( self ) -> Redis:

        return self._client

    async def get ( self, key: str ) -> object | None:

        raw = await self.guard(self._client.get(self.key(key)))

        return json.loads(raw) if raw else None

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None:

        await self.guard(self._client.set(self.key(key), json.encode(value), px=self.millis(ttl)))

    async def add ( self, key: str, value: object, ttl: float | None = None ) -> bool:

        stored = await self.guard(self._client.set(self.key(key), json.encode(value), px=self.millis(ttl), nx=True))

        return bool(stored)

    async def delete ( self, key: str ) -> bool:

        return bool(await self.guard(self._client.delete(self.key(key))))

    async def increment ( self, key: str, step: int = 1, ttl: float | None = None ) -> int:

        span  = int(ttl * MILLI) if ttl else 0
        value = await self.guard(self._client.eval(COUNT, 1, self.key(key), step, span))

        return int(value)

    async def ttl ( self, key: str ) -> float | None:

        left = int(await self.guard(self._client.pttl(self.key(key))))

        return left / MILLI if left >= 0 else None

    async def touch ( self, key: str, ttl: float ) -> bool:

        return bool(await self.guard(self._client.pexpire(self.key(key), int(ttl * MILLI))))

    async def many ( self, keys: Iterable[str] ) -> dict[str, object | None]:

        wanted = list(keys)

        if not wanted: return {}

        found = await self.guard(self._client.mget([self.key(key) for key in wanted]))

        return { key: json.loads(raw) if raw else None for key, raw in zip(wanted, found, strict=True) }

    async def release ( self, key: str, owner: str ) -> bool:

        freed = await self.guard(self._client.eval(RELEASE, 1, self.key(key), json.encode(owner)))

        return bool(freed)

    async def clear ( self ) -> int:

        batch: list[str] = []
        count = 0

        async for found in self._client.scan_iter(match=f"{self._prefix}:*", count=BATCH):

            batch.append(found)

            if len(batch) >= BATCH:

                count += int(await self.guard(self._client.delete(*batch)))

                batch.clear()

        if batch: count += int(await self.guard(self._client.delete(*batch)))

        return count

    async def ping ( self ) -> bool:

        try: return bool(await self._client.ping())
        except RedisError: return False

    async def close ( self ) -> None:

        await self._client.aclose()

    def millis ( self, ttl: float | None ) -> int | None:

        return int(ttl * MILLI) if ttl else None

    async def guard ( self, call: Any ) -> Any:

        try: return await call
        except RedisError as error: raise Fault(Code.UNAVAILABLE, reason="cache") from error
