from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from core.event import Event, events
from core.exceptions import Code, Fault
from core.log import log
from core.socket import Connection, Grant, Socket
import inspect, re

type Verdict = Grant | Mapping[str, Any] | bool | None
type Authorize = Callable[..., Awaitable[Verdict] | Verdict]
type Guard = Callable[[str | None], Awaitable[Any]]

PRIVATE  = "private-"
PRESENCE = "presence-"
PARAM    = re.compile(r"\{(\w+)\}")

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int: ...

class LocalDriver:

    name = "local"

    def __init__ ( self, socket: Socket ) -> None:

        self._socket = socket

    def publish ( self, channel: str, event: str, data: Any, exclude: str | None ) -> int:
        return self._socket.publish(channel, event, data, exclude)

@dataclass(frozen=True, slots=True)
class Channel:

    pattern   : str
    matcher   : re.Pattern[str]
    authorize : Authorize | None
    guests    : bool = False

    def match ( self, name: str ) -> dict[str, str] | None:

        found = self.matcher.fullmatch(name)

        return found.groupdict() if found else None

class Broadcast:

    def __init__ ( self ) -> None:

        self._channels: list[Channel] = []
        self._socket: Socket | None = None
        self._driver: Driver | None = None
        self._guard: Guard | None = None

    def setup ( self, socket: Socket, guard: Guard | None = None, driver: Driver | None = None ) -> None:

        self._socket = socket
        self._guard  = guard
        self._driver = driver or LocalDriver(socket)

        socket.setup(authorizer=self.grant)
        events.on_any(self.relay)

    def ready ( self ) -> bool:
        return self._driver is not None

    def channel ( self, pattern: str, authorize: Authorize | None = None, guests: bool = False ) -> Channel:

        escaped = re.escape(pattern).replace(r"\{", "{").replace(r"\}", "}")
        regex   = PARAM.sub(lambda found: f"(?P<{found.group(1)}>[^.]+)", escaped)
        channel = Channel(pattern, re.compile(regex), authorize, guests)

        self._channels.append(channel)

        return channel

    def public ( self, pattern: str ) -> Channel:
        return self.channel(pattern, None, guests=True)

    def channels ( self ) -> list[str]:
        return [channel.pattern for channel in self._channels]

    def find ( self, name: str ) -> tuple[Channel, dict[str, str]] | None:

        for channel in self._channels:

            params = channel.match(name)

            if params is not None: return channel, params

        return None

    def kind ( self, name: str ) -> str:

        if name.startswith(PRESENCE): return "presence"
        if name.startswith(PRIVATE): return "private"

        return "public"

    def bare ( self, name: str ) -> str:

        for prefix in (PRESENCE, PRIVATE):
            if name.startswith(prefix): return name[len(prefix):]

        return name

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

    def emit ( self, channels: str | Sequence[str], event: str, data: Any = None, exclude: str | None = None ) -> int:

        if self._driver is None: raise Fault(Code.INTERNAL, reason="broadcast")

        names   = (channels,) if isinstance(channels, str) else tuple(channels)
        reached = sum(self._driver.publish(name, event, data, exclude) for name in names)

        log.debug("broadcast.emitted", name=event, channels=list(names), reached=reached)

        return reached

    def to ( self, *channels: str ) -> Emission:
        return Emission(self, channels)

    async def relay ( self, event: Event ) -> None:

        channels = tuple(event.channels())

        if channels and self._driver is not None: self.emit(channels, event.label(), event.payload())

    def socket ( self ) -> Socket:

        if self._socket is None: raise Fault(Code.INTERNAL, reason="broadcast")

        return self._socket

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
