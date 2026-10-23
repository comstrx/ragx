from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from engine.error import Code, Fault
from engine.json import json
from engine.log import log
from engine.rand import rand
from engine.socket import Socket
from engine.thread import thread
import asyncio

PAUSE   = 0.1
CEILING = 5.0

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int: ...

    async def deliver ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int: ...

    async def start ( self ) -> None: ...

    async def stop ( self ) -> None: ...

class LocalDriver:

    name = "local"

    def __init__ ( self, socket: Socket ) -> None:

        self._socket = socket

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:

        return self._socket.publish(channel, event, data, exclude)

    async def deliver ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:

        return self.publish(channel, event, data, exclude)

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
        self._lost    = 0

    def origin ( self ) -> str:

        return self._origin

    def packet ( self, channel: str, event: str, data: Any ) -> bytes:

        return json.encode({ "origin": self._origin, "channel": channel, "event": event, "data": data })

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:

        reached = self._socket.publish(channel, event, data, exclude)

        thread.tasks.fire(self.forward(self.packet(channel, event, data)), "broadcast:forward")

        return reached

    async def deliver ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:

        try: await self._client.publish(self._topic, self.packet(channel, event, data))
        except RedisError as error:
            raise Fault(Code.UNAVAILABLE, reason="broadcast.redis", unknown=isinstance(error, TimeoutError)) from error

        return self._socket.publish(channel, event, data, exclude)

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

        pause = PAUSE

        try:

            while True:

                try:

                    async for message in pubsub.listen():

                        pause = PAUSE

                        if message.get("type") == "message": self.relay(json.parse(message.get("data")))

                except RedisError:

                    self._lost += 1

                    log.warning("broadcast.redis_lost", retry=pause)

                    await asyncio.sleep(pause)

                    pause = min(pause * 2, CEILING)

                else: return

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
            "topic": self._topic, "origin": self._origin, "relayed": self._relayed, "lost": self._lost,
            "listening": self._reader is not None,
        }
