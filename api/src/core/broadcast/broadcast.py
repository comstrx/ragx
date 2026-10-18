from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from core.event import Event, events
from core.error import Code, Fault
from core.log import log
from core.socket import Connection, Grant, Socket
from .channel import Authorize, Channel, Channels, Verdict
from .driver import Driver, LocalDriver
import inspect

type Guard = Callable[[str | None], Awaitable[Any]]

class Broadcast:

    def __init__ ( self ) -> None:

        self._channels = Channels()
        self._socket: Socket | None = None
        self._driver: Driver | None = None
        self._guard: Guard | None = None
        self._emitted = 0

    def setup ( self, socket: Socket, guard: Guard | None = None, driver: Driver | None = None ) -> None:

        self._socket = socket
        self._guard  = guard
        self._driver = driver or LocalDriver(socket)

        socket.setup(authorizer=self.grant)
        events.on_any(self.relay)

    def ready ( self ) -> bool:
        return self._driver is not None

    def registry ( self ) -> Channels:
        return self._channels

    def channel ( self, pattern: str, authorize: Authorize | None = None, guests: bool = False ) -> Channel:
        return self._channels.channel(pattern, authorize, guests)

    def public ( self, pattern: str ) -> Channel:
        return self._channels.public(pattern)

    def channels ( self ) -> list[str]:
        return self._channels.patterns()

    def find ( self, name: str ) -> tuple[Channel, dict[str, str]] | None:
        return self._channels.find(name)

    def kind ( self, name: str ) -> str:
        return self._channels.kind(name)

    def bare ( self, name: str ) -> str:
        return self._channels.bare(name)

    async def grant ( self, connection: Connection, name: str, auth: str | None ) -> Grant:

        kind  = self.kind(name)
        found = self.find(self.bare(name))

        if kind == "public": return Grant(allowed=True)
        if found is None: return Grant(reason=f"channel.{name}.unknown")

        channel, params = found

        if connection.user is None and self._guard is not None and auth:

            try: connection.user = await self._guard(auth)
            except Fault as fault: return Grant(reason=fault.reason or "channel.auth")

        if connection.user is None and not channel.guests: return Grant(reason="channel.auth")

        return self.verdict(await self.decide(channel, connection.user, params), kind)

    async def decide ( self, channel: Channel, user: Any, params: Mapping[str, str] ) -> Verdict:

        if channel.authorize is None: return True

        result = channel.authorize(user, **params)

        if inspect.isawaitable(result): return await result

        return result

    def verdict ( self, decision: Verdict, kind: str ) -> Grant:

        if isinstance(decision, Grant): return decision
        if isinstance(decision, Mapping): return Grant(allowed=True, member=dict(decision), publish=kind == "presence")
        if decision: return Grant(allowed=True, publish=kind == "presence")

        return Grant(reason="channel.denied")

    def driver ( self ) -> Driver:

        if self._driver is None: raise Fault(Code.INTERNAL, reason="broadcast")

        return self._driver

    def emit ( self, channels: str | Sequence[str], event: str, data: Any = None, exclude: str | None = None ) -> int:

        driver  = self.driver()
        names   = (channels,) if isinstance(channels, str) else tuple(channels)
        reached = sum(driver.publish(name, event, data, exclude) for name in names)

        self._emitted += 1

        log.debug("broadcast.emitted", name=event, channels=list(names), reached=reached)

        return reached

    def to ( self, *channels: str ) -> Emission:
        return Emission(self, channels)

    def to_user ( self, user_id: str ) -> Emission:
        return Emission(self, (f"private-users.{user_id}",))

    def to_everyone ( self, event: str, data: Any = None ) -> int:
        return self.socket().broadcast(event, data)

    async def relay ( self, event: Event ) -> None:

        channels = tuple(event.channels())

        if channels and self._driver is not None: self.emit(channels, event.label(), event.payload())

    def socket ( self ) -> Socket:

        if self._socket is None: raise Fault(Code.INTERNAL, reason="broadcast")

        return self._socket

    async def start ( self ) -> None:

        if self._driver is not None: await self._driver.start()

    async def stop ( self ) -> None:

        if self._driver is not None: await self._driver.stop()

    def describe ( self ) -> dict[str, Any]:

        return {
            "driver": self._driver.name if self._driver else None, "channels": self._channels.describe(),
            "emitted": self._emitted, "socket": self._socket.stats() if self._socket else None,
        }

class Emission:

    def __init__ ( self, owner: Broadcast, channels: tuple[str, ...] ) -> None:

        self._owner    = owner
        self._channels = channels
        self._exclude: str | None = None

    def except_ ( self, socket_id: str | None ) -> Emission:

        self._exclude = socket_id

        return self

    def send ( self, event: str, data: Any = None ) -> int:
        return self._owner.emit(self._channels, event, data, self._exclude)

    def send_event ( self, event: Event ) -> int:
        return self._owner.emit(self._channels, event.label(), event.payload(), self._exclude)
