from collections.abc import Awaitable, Callable
from typing import Any

from engine.error import Code, Fault
from engine.rand import rand
from starlette.websockets import WebSocket, WebSocketDisconnect
from .connection import POLICY, PRESENCE, PRIVATE, TOO_BIG, TRY_AGAIN, Connection, Frame, Grant, Limits
from .hub import Hub
import asyncio

type Authorizer = Callable[[Connection, str, str | None], Awaitable[Grant]]

PING = "ping"

class Socket(Hub):

    def __init__ ( self ) -> None:

        super().__init__()

        self._authorizer: Authorizer | None = None

    def setup ( self, limits: Limits | None = None, authorizer: Authorizer | None = None ) -> None:

        if limits is not None: self._limits = limits
        if authorizer is not None: self._authorizer = authorizer

    @property
    def endpoint ( self ) -> Callable[..., Awaitable[None]]:

        return self._serve_

    async def _serve_ ( self, websocket: WebSocket ) -> None:

        if self.full():

            await websocket.close(TRY_AGAIN, "full")

            return

        await websocket.accept()

        connection = Connection(str(rand.uuid()), websocket, websocket.query_params.get("token"))

        connection.outbox = asyncio.Queue(self._limits.queue)
        connection.writer = asyncio.create_task(connection.pump(), name=f"socket:{connection.id}")

        self.attach(connection)
        connection.emit("connected", { "socket_id": connection.id, "ping": self._limits.ping })

        try: await self.listen(connection)
        except WebSocketDisconnect: pass
        finally: await self.detach(connection)

    async def listen ( self, connection: Connection ) -> None:

        idle = 0

        while not connection.closed:

            try:
                async with asyncio.timeout(self._limits.ping): raw = await self.receive(connection)
            except TimeoutError:

                idle += 1

                if idle > 1:

                    await connection.close(POLICY, "timeout")

                    return

                connection.emit(PING)

                continue

            idle = 0

            if len(raw) > self._limits.frame:

                await connection.close(TOO_BIG, "frame")

                return

            connection.received += 1

            await self.handle(connection, raw)

    async def receive ( self, connection: Connection ) -> str:

        message = await connection.socket.receive()

        if message.get("type") == "websocket.disconnect": raise WebSocketDisconnect(int(message.get("code", 1000)))

        data = message.get("bytes")

        return bytes(data).decode(errors="replace") if data is not None else str(message.get("text") or "")

    async def handle ( self, connection: Connection, raw: str ) -> None:

        try: await self.command(connection, Frame.command(raw))
        except Fault as fault: self.refuse(connection, fault)

    def refuse ( self, connection: Connection, fault: Fault ) -> None:

        connection.emit("error", { "code": fault.code, "reason": fault.reason })

    async def command ( self, connection: Connection, frame: Frame ) -> None:

        if frame.event == "ping": connection.offer(frame.reply("pong").encode())
        if frame.event == "subscribe": await self.subscribe(connection, frame)
        if frame.event == "unsubscribe": await self.unsubscribe(connection, frame)
        if frame.event == "publish": await self.whisper(connection, frame)

    async def subscribe ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""

        if not channel: raise Fault(Code.BAD_REQUEST, reason="channel")

        grant = await self.grant(connection, channel, frame.auth() or connection.token)

        if not grant.allowed: raise Fault(Code.FORBIDDEN, reason=grant.reason or f"channel.{channel}")

        self.join(connection, channel, grant)

        data: dict[str, Any] = { "channel": channel }

        if channel.startswith(PRESENCE):

            data["members"] = self.members(channel)

            self.publish(channel, "member_joined", { "member": grant.member }, exclude=connection.id)

        connection.offer(frame.reply("subscribed", data).encode())

        if self._joined is not None: await self.hook(self._joined, connection)

    async def unsubscribe ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""

        if channel: self.leave(connection, channel)

        connection.offer(frame.reply("unsubscribed", { "channel": channel }).encode())

    async def whisper ( self, connection: Connection, frame: Frame ) -> None:

        channel = frame.channel or ""
        grant   = connection.channels.get(channel)
        payload = frame.data if isinstance(frame.data, dict) else {}
        event   = str(payload.get("event") or "")

        if grant is None or not grant.publish: raise Fault(Code.FORBIDDEN, reason="channel.publish")
        if not event: raise Fault(Code.BAD_REQUEST, reason="frame.event")

        self.publish(channel, event, { "from": grant.member, "data": payload.get("data") }, exclude=connection.id)

    async def grant ( self, connection: Connection, channel: str, auth: str | None ) -> Grant:

        if self._authorizer is None: return Grant(not channel.startswith((PRIVATE, PRESENCE)))

        return await self._authorizer(connection, channel, auth)
