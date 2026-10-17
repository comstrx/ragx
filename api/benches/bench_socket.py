from starlette.websockets import WebSocketState
from core.socket import Connection, Grant, Socket
from benches import Bench
import asyncio

class Sink:

    client_state = WebSocketState.CONNECTED

    def __init__ ( self ) -> None:

        self.count = 0

    async def send_bytes ( self, _data: bytes ) -> None:
        self.count += 1

    async def receive ( self ) -> dict[str, object]:
        return { "type": "websocket.disconnect", "code": 1000 }

    async def close ( self, _code: int = 1000, _reason: str | None = None ) -> None:
        return None

class SocketBench(Bench):

    connections = 2000
    publishes   = 500

    async def run ( self ) -> None:

        self.quiet()

        hub   = Socket()
        sinks = [Sink() for _ in range(self.connections)]

        for index, sink in enumerate(sinks):

            connection = hub.attach(Connection(str(index), sink, outbox=asyncio.Queue(1024)))

            connection.writer = asyncio.create_task(connection.pump())

            hub.join(connection, "feed", Grant(allowed=True))

        async def publish () -> None:

            reached = hub.publish("feed", "tick", { "n": 1 })

            self.expect("fan-out", reached, self.connections)

        latencies, elapsed = await self.measure(publish, self.publishes, 1)

        await asyncio.sleep(0.5)

        delivered = sum(sink.count for sink in sinks)

        self.expect("delivered", delivered, self.connections * self.publishes)
        self.report("publish", latencies, elapsed, 25.0)

        rate = delivered / (elapsed + 0.5)

        print(f"{'frames':<14} {delivered:>8,} delivered · {rate:>12,.0f} frames/s to {self.connections} sockets")

        await hub.close_all()

if __name__ == "__main__":

    asyncio.run(SocketBench().run())
