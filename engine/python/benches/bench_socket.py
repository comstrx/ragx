from typing import override

from engine.socket import Connection, Grant, Socket
from engine.test import Bench, Stub
import asyncio

class Sink(Stub):

    def __init__ ( self ) -> None:

        super().__init__()

        self.count = 0

    @override
    async def send_bytes ( self, data: bytes ) -> None:

        self.count += 1

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
