from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from core.log import log
from core.thread import thread
from .connection import GOING_AWAY, POLICY, PRESENCE, Connection, Grant, Limits
from .frame import Frame

type Hook = Callable[[Connection], Awaitable[None] | None]

class Hub:

    def __init__ ( self ) -> None:

        self._connections: dict[str, Connection] = {}
        self._topics: dict[str, set[str]] = {}
        self._joined: Hook | None = None
        self._left: Hook | None = None
        self._limits    = Limits()
        self._published = 0
        self._dropped   = 0

    def limits ( self ) -> Limits:

        return self._limits

    def on_join ( self, hook: Hook ) -> None:

        self._joined = hook

    def on_leave ( self, hook: Hook ) -> None:

        self._left = hook

    def full ( self ) -> bool:

        return len(self._connections) >= self._limits.connections

    def attach ( self, connection: Connection ) -> Connection:

        self._connections[connection.id] = connection

        return connection

    def join ( self, connection: Connection, channel: str, grant: Grant | None = None ) -> None:

        connection.channels[channel] = grant or Grant(allowed=True)
        self._topics.setdefault(channel, set()).add(connection.id)

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

    def send_to_user ( self, user_id: str, event: str, data: Any = None ) -> int:

        return sum(1 for connection in self.connections_of(user_id) if connection.emit(event, data))

    def broadcast ( self, event: str, data: Any = None, exclude: str | None = None ) -> int:

        encoded = Frame(event, None, data).encode()
        others  = [connection for identity, connection in list(self._connections.items()) if identity != exclude]

        return sum(1 for connection in others if connection.offer(encoded))

    def throttle ( self, connection: Connection ) -> None:

        self._dropped += 1

        if connection.dropped >= self._limits.drops:

            log.warning("socket.slow_consumer", connection=connection.id, dropped=connection.dropped)
            thread.tasks.fire(connection.close(POLICY, "slow"), "socket:shed")

    async def kick ( self, identity: str, reason: str = "kicked" ) -> bool:

        connection = self._connections.get(identity)

        if connection is None: return False

        await connection.close(POLICY, reason)
        await self.detach(connection)

        return True

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

    def connections_of ( self, user_id: str ) -> list[Connection]:

        return [connection for connection in self._connections.values() if connection.user_id() == user_id]

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

    def describe ( self ) -> dict[str, Any]:

        limits = self._limits

        return {
            **self.stats(),
            "limits": { "connections": limits.connections, "queue": limits.queue, "frame": limits.frame },
        }

    async def close_all ( self, reason: str = "shutdown" ) -> int:

        connections = list(self._connections.values())

        for connection in connections:

            await connection.close(GOING_AWAY, reason)
            await self.detach(connection)

        return len(connections)
