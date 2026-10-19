from typing import Any

from core.error import Code, Fault
import asyncio, socket

class Probe:

    async def resolve ( self, host: str, wait: float = 3.0 ) -> list[str]:

        loop = asyncio.get_running_loop()

        try:
            async with asyncio.timeout(wait):
                found = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except (OSError, TimeoutError): return []

        return sorted({ str(entry[4][0]) for entry in found })

    async def port_open ( self, host: str, port: int, wait: float = 2.0 ) -> bool:

        try:
            async with asyncio.timeout(wait):
                _, writer = await asyncio.open_connection(host, port)
        except (OSError, TimeoutError): return False

        writer.close()

        await writer.wait_closed()

        return True

    async def wait_port ( self, host: str, port: int, within: float = 30.0, every: float = 0.5 ) -> bool:

        loop     = asyncio.get_running_loop()
        deadline = loop.time() + within

        while True:

            if await self.port_open(host, port, min(every * 4, 5.0)): return True
            if loop.time() >= deadline: return False

            await asyncio.sleep(every)

    async def require_port ( self, host: str, port: int, within: float = 30.0 ) -> None:

        if not await self.wait_port(host, port, within): raise Fault(Code.UNAVAILABLE, reason=f"{host}:{port}")

    def free_port ( self, host: str = "127.0.0.1" ) -> int:

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:

            probe.bind((host, 0))

            return int(probe.getsockname()[1])

    def local_ip ( self ) -> str:

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:

            try:

                probe.connect(("10.255.255.255", 1))

                return str(probe.getsockname()[0])

            except OSError: return "127.0.0.1"

    def hostname ( self ) -> str:

        return socket.gethostname()

    def describe_host ( self ) -> dict[str, Any]:

        return { "hostname": self.hostname(), "ip": self.local_ip() }
