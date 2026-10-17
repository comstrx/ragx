from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from core.date import date
from core.exceptions import Code, Fault
from core.log import log
from core.rand import rand
from .protocol import Frame
import asyncio

type Authorizer = Callable[["Connection", str, str | None], Awaitable["Grant"]]
type Hook = Callable[["Connection"], Awaitable[None] | None]

PRESENCE    = "presence-"
PRIVATE     = "private-"
TOO_BIG     = 1009
POLICY      = 1008
GOING_AWAY  = 1001
TRY_AGAIN   = 1013
PING        = "ping"
COMMANDS    = frozenset({"subscribe", "unsubscribe", "ping", "pong", "publish"})

class Transport(Protocol):

    @property
    def client_state ( self ) -> WebSocketState: ...

    async def send_bytes ( self, data: bytes ) -> None: ...

    async def receive_text ( self ) -> str: ...

    async def close ( self, code: int = 1000, reason: str | None = None ) -> None: ...

@dataclass(frozen=True, slots=True)
class Grant:

    allowed : bool = False
    member  : Mapping[str, Any] | None = None
    publish : bool = False
    reason  : str | None = None

@dataclass(slots=True)
class Limits:

    connections : int = 10_000
    queue       : int = 256
    frame       : int = 64 * 1024
    ping        : float = 25.0
    drops       : int = 64

@dataclass(slots=True)
class Connection:

    id       : str
    socket   : Transport
    token    : str | None = None
    user     : Any = None
    channels : dict[str, Grant] = field(default_factory=dict)
    outbox   : asyncio.Queue[bytes] = field(default_factory=asyncio.Queue)
    opened   : float = field(default_factory=date.stamp)
    sent     : int = 0
    dropped  : int = 0
    closed   : bool = False
    writer   : asyncio.Task[None] | None = None

    def offer ( self, data: bytes ) -> bool:

        if self.closed: return False

        try: self.outbox.put_nowait(data)
        except asyncio.QueueFull:

            self.dropped += 1

            return False

        return True

    async def pump ( self ) -> None:

        while not self.closed:

            data = await self.outbox.get()

            if self.socket.client_state != WebSocketState.CONNECTED: break

            await self.socket.send_bytes(data)

            self.sent += 1

    async def close ( self, code: int = GOING_AWAY, reason: str = "" ) -> None:

        if self.closed: return

        self.closed = True

        if self.writer is not None: self.writer.cancel()
        if self.socket.client_state == WebSocketState.CONNECTED: await self.socket.close(code, reason)

    def presence ( self ) -> list[str]:
        return [name for name in self.channels if name.startswith(PRESENCE)]

    def describe ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "channels": sorted(self.channels), "sent": self.sent, "dropped": self.dropped,
            "age": round(date.stamp() - self.opened, 3),
        }

class Socket:

    def __init__ ( self ) -> None:

        self._connections: dict[str, Connection] = {}
        self._topics: dict[str, set[str]] = {}
        self._authorizer: Authorizer | None = None
        self._joined: Hook | None = None
        self._left: Hook | None = None
        self._limits = Limits()
        self._published = 0
        self._dropped = 0

    def setup ( self, limits: Limits | None = None, authorizer: Authorizer | None = None ) -> None:

        if limits is not None: self._limits = limits
        if authorizer is not None: self._authorizer = authorizer

    def on_join ( self, hook: Hook ) -> None:
        self._joined = hook

    def on_leave ( self, hook: Hook ) -> None:
        self._left = hook

    def limits ( self ) -> Limits:
        return self._limits

    async def endpoint ( self, websocket: WebSocket ) -> None:

        if len(self._connections) >= self._limits.connections:

            await websocket.close(TRY_AGAIN, "full")

            return

        await websocket.accept()

        connection = Connection(str(rand.uuid()), websocket, websocket.query_params.get("token"))

        connection.outbox = asyncio.Queue(self._limits.queue)
        connection.writer = asyncio.create_task(connection.pump(), name=f"socket:{connection.id}")

        self.attach(connection)
        connection.offer(Frame("connected", data={ "socket_id": connection.id, "ping": self._limits.ping }).encode())

        try: await self.listen(connection)
        except WebSocketDisconnect: pass
        finally: await self.detach(connection)

    async def listen ( self, connection: Connection ) -> None:

        idle = 0

        while not connection.closed:

            try:
                async with asyncio.timeout(self._limits.ping): raw = await connection.socket.receive_text()
            except TimeoutError:

                idle += 1

                if idle > 1:

                    await connection.close(POLICY, "timeout")

                    return

                connection.offer(Frame(PING).encode())

                continue

            idle = 0

            if len(raw) > self._limits.frame:

                await connection.close(TOO_BIG, "frame")

                return

            await self.handle(connection, raw)

    async def handle ( self, connection: Connection, raw: str ) -> None:

        try: await self.command(connection, self.parse(raw))
        except Fault as fault: self.refuse(connection, fault)

    def parse ( self, raw: str ) -> Frame:

        frame = Frame.decode(raw)

        if frame.event not in COMMANDS: raise Fault(Code.BAD_REQUEST, reason="frame.command")

        return frame

    def refuse ( self, connection: Connection, fault: Fault ) -> None:
        connection.offer(Frame("error", data={ "code": fault.code, "reason": fault.reason }).encode())

    async def command ( self, connection: Connection, frame: Frame ) -> None:

        if frame.event == "ping": connection.offer(frame.reply("pong").encode())
        if frame.event == "subscribe": await self.subscribe(connection, frame)
        if frame.event == "unsubscribe": await self.unsubscribe(connection, frame)
        if frame.event == "publish": await self.whisper(connection, frame)

    async def subscribe ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""
        auth    = frame.data.get("auth") if isinstance(frame.data, Mapping) else None

        if not channel: raise Fault(Code.BAD_REQUEST, reason="channel")

        grant = await self.grant(connection, channel, auth if isinstance(auth, str) else connection.token)

        if not grant.allowed: raise Fault(Code.FORBIDDEN, reason=grant.reason or f"channel.{channel}")

        self.join(connection, channel, grant)

        data: dict[str, Any] = { "channel": channel }

        if channel.startswith(PRESENCE):

            data["members"] = self.members(channel)

            self.publish(channel, "member_joined", { "member": grant.member }, exclude=connection.id)

        connection.offer(frame.reply("subscribed", data).encode())

        if self._joined is not None: await self.hook(self._joined, connection)

    def attach ( self, connection: Connection ) -> Connection:

        self._connections[connection.id] = connection

        return connection

    def join ( self, connection: Connection, channel: str, grant: Grant | None = None ) -> None:

        connection.channels[channel] = grant or Grant(allowed=True)
        self._topics.setdefault(channel, set()).add(connection.id)

    async def unsubscribe ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""

        if channel: self.leave(connection, channel)

        connection.offer(frame.reply("unsubscribed", { "channel": channel }).encode())

    async def whisper ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""
        grant   = connection.channels.get(channel)
        payload = frame.data if isinstance(frame.data, Mapping) else {}
        event   = str(payload.get("event") or "")

        if grant is None or not grant.publish: raise Fault(Code.FORBIDDEN, reason="channel.publish")
        if not event: raise Fault(Code.BAD_REQUEST, reason="frame.event")

        self.publish(channel, event, { "from": grant.member, "data": payload.get("data") }, exclude=connection.id)

    async def grant ( self, connection: Connection, channel: str, auth: str | None ) -> Grant:

        if self._authorizer is None: return Grant(not channel.startswith((PRIVATE, PRESENCE)))

        return await self._authorizer(connection, channel, auth)

    def leave ( self, connection: Connection, channel: str ) -> None:

        grant = connection.channels.pop(channel, None)
        group = self._topics.get(channel)

        if group is not None:

            group.discard(connection.id)

            if not group: del self._topics[channel]

        if grant is not None and channel.startswith(PRESENCE):
            self.publish(channel, "member_left", { "member": grant.member }, exclude=connection.id)

    async def detach ( self, connection: Connection ) -> None:

        for channel in list(connection.channels): self.leave(connection, channel)

        self._connections.pop(connection.id, None)

        await connection.close()

        if self._left is not None: await self.hook(self._left, connection)

    async def hook ( self, hook: Hook, connection: Connection ) -> None:

        result = hook(connection)

        if result is not None: await result

    def publish ( self, channel: str, event: str, data: Any = None, exclude: str | None = None ) -> int:

        group = self._topics.get(channel)

        if not group: return 0

        encoded = Frame(event, channel, data).encode()
        reached = 0

        for identity in list(group):

            connection = self._connections.get(identity)

            if connection is None or identity == exclude: continue

            if connection.offer(encoded): reached += 1
            else: self.throttle(connection)

        self._published += 1

        return reached

    def send ( self, identity: str, event: str, data: Any = None ) -> bool:

        connection = self._connections.get(identity)

        return connection is not None and connection.offer(Frame(event, None, data).encode())

    def throttle ( self, connection: Connection ) -> None:

        self._dropped += 1

        if connection.dropped >= self._limits.drops:

            log.warning("socket.slow_consumer", connection=connection.id, dropped=connection.dropped)
            asyncio.get_running_loop().create_task(connection.close(POLICY, "slow"))

    def members ( self, channel: str ) -> list[Mapping[str, Any]]:

        found = []

        for identity in self._topics.get(channel, ()):

            connection = self._connections.get(identity)
            grant      = connection.channels.get(channel) if connection else None

            if grant is not None and grant.member is not None: found.append(grant.member)

        return found

    def connection ( self, identity: str ) -> Connection | None:
        return self._connections.get(identity)

    def connections ( self ) -> list[Connection]:
        return list(self._connections.values())

    def channels ( self ) -> dict[str, int]:
        return { channel: len(group) for channel, group in sorted(self._topics.items()) }

    def subscribers ( self, channel: str ) -> int:
        return len(self._topics.get(channel, ()))

    def stats ( self ) -> dict[str, int]:

        return {
            "connections" : len(self._connections),
            "channels"    : len(self._topics),
            "published"   : self._published,
            "dropped"     : self._dropped,
        }

    async def close_all ( self, reason: str = "shutdown" ) -> int:

        connections = list(self._connections.values())

        for connection in connections:

            await connection.close(GOING_AWAY, reason)
            await self.detach(connection)

        return len(connections)
