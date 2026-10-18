from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from core.error import Code, Fault
from core.json import json
from core.log import log
from core.rand import rand
from core.socket import Socket
import asyncio

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int: ...

    async def start ( self ) -> None: ...

    async def stop ( self ) -> None: ...

class LocalDriver:

    name = "local"

    def __init__ ( self, socket: Socket ) -> None:

        self._socket = socket

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:
        return self._socket.publish(channel, event, data, exclude)

    async def start ( self ) -> None:
        return None

    async def stop ( self ) -> None:
        return None

class RedisDriver:

    name = "redis"

    def __init__ ( self, socket: Socket, url: str, topic: str = "broadcast", wait: float = 2.0 ) -> None:

        self._socket = socket
        self._topic  = topic
        self._origin = str(rand.uuid())
        self._client: Redis = Redis.from_url(url, socket_connect_timeout=wait, socket_timeout=wait)
        self._reader: asyncio.Task[None] | None = None
        self._relayed = 0

    def origin ( self ) -> str:
        return self._origin

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:

        reached = self._socket.publish(channel, event, data, exclude)
        payload = json.encode({ "origin": self._origin, "channel": channel, "event": event, "data": data })

        asyncio.get_running_loop().create_task(self.forward(payload), name="broadcast:forward")

        return reached

    async def forward ( self, payload: bytes ) -> None:

        try: await self._client.publish(self._topic, payload)
        except RedisError: log.warning("broadcast.redis_unreachable")

    async def start ( self ) -> None:

        if self._reader is not None: return

        pubsub = self._client.pubsub()

        try: await pubsub.subscribe(self._topic)
        except RedisError as error: raise Fault(Code.UNAVAILABLE, reason="broadcast") from error

        self._reader = asyncio.create_task(self.listen(pubsub), name="broadcast:redis")

    async def listen ( self, pubsub: Any ) -> None:

        try:

            async for message in pubsub.listen():

                if message.get("type") != "message": continue

                self.relay(json.parse(message.get("data")))

        except RedisError: log.warning("broadcast.redis_lost")
        finally: await cast("Any", pubsub).aclose()

    def relay ( self, packet: Any ) -> int:

        if not isinstance(packet, dict) or packet.get("origin") == self._origin: return 0

        self._relayed += 1

        channel = str(packet.get("channel", ""))

        return self._socket.publish(channel, str(packet.get("event", "")), packet.get("data"), None)

    async def stop ( self ) -> None:

        reader, self._reader = self._reader, None

        if reader is not None:

            reader.cancel()

            await asyncio.gather(reader, return_exceptions=True)

        await self._client.aclose()

    def describe ( self ) -> dict[str, object]:

        return {
            "topic": self._topic, "origin": self._origin, "relayed": self._relayed,
            "listening": self._reader is not None,
        }
