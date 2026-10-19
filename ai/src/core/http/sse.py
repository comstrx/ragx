from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from starlette.responses import StreamingResponse
from core.json import json
import asyncio

type Packet = Sse | Mapping[str, Any] | str | bytes

HEADERS = { "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive" }
PING    = 15.0

@dataclass(frozen=True, slots=True)
class Sse:

    data  : Any
    event : str | None = None
    id    : str | None = None
    retry : int | None = None

    def encode ( self ) -> bytes:

        lines: list[str] = []

        if self.event: lines.append(f"event: {self.event}")
        if self.id: lines.append(f"id: {self.id}")
        if self.retry: lines.append(f"retry: {int(self.retry)}")

        text = self.data if isinstance(self.data, str) else json.dumps(self.data)

        lines.extend(f"data: {line}" for line in text.split("\n"))

        return ("\n".join(lines) + "\n\n").encode()

    @staticmethod
    def comment ( text: str = "ping" ) -> bytes:

        return f": {text}\n\n".encode()

    @staticmethod
    def pack ( packet: Packet ) -> bytes:

        if isinstance(packet, Sse): return packet.encode()
        if isinstance(packet, bytes): return packet
        if isinstance(packet, str): return Sse(packet).encode()

        return Sse(
            packet.get("data"), packet.get("event"), packet.get("id"), packet.get("retry"),
        ).encode() if "data" in packet else Sse(dict(packet)).encode()

class EventStream(StreamingResponse):

    def __init__ (
        self, source: AsyncIterator[Packet], ping: float = PING, status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:

        super().__init__(
            self.pulse(source, ping), status_code=status, media_type="text/event-stream",
            headers={ **HEADERS, **(headers or {}) },
        )

    @staticmethod
    async def pulse ( source: AsyncIterator[Packet], ping: float ) -> AsyncIterator[bytes]:

        iterator = source.__aiter__()

        while True:

            try:
                async with asyncio.timeout(ping if ping > 0 else None): packet = await iterator.__anext__()
            except TimeoutError:

                yield Sse.comment()

                continue

            except StopAsyncIteration: return

            yield Sse.pack(packet)
