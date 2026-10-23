from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

from engine.error import Fault
from engine.json import json
from starlette.responses import StreamingResponse
import asyncio, contextlib

type Packet = Sse | Mapping[str, Any] | str | bytes

HEADERS = { "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive" }
PING    = 15.0
BUFFER  = 16
END     = object()

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
    def failed ( fault: Fault ) -> Sse:

        return Sse({ "code": fault.code.value, "reason": fault.reason, "message": fault.message }, "error")

    @staticmethod
    def pack ( packet: Packet ) -> bytes:

        if isinstance(packet, Sse): return packet.encode()
        if isinstance(packet, bytes): return packet
        if isinstance(packet, str): return Sse(packet).encode()

        return Sse(
            packet.get("data"), packet.get("event"), packet.get("id"), packet.get("retry"),
        ).encode() if "data" in packet else Sse(dict(packet)).encode()

async def drained ( source: AsyncIterator[Packet], queue: asyncio.Queue[object] ) -> None:

    try:

        async for packet in source: await queue.put(packet)

    except Fault as fault: await queue.put(Sse.failed(fault))

    await queue.put(END)

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

        queue    : asyncio.Queue[object] = asyncio.Queue(BUFFER)
        producer : asyncio.Future[Any] = asyncio.ensure_future(drained(source, queue))
        getter   : asyncio.Future[Any] | None = None
        wait     = ping if ping > 0 else None

        try:

            while True:

                getter  = getter or asyncio.ensure_future(queue.get())
                done, _ = await asyncio.wait({ getter, producer }, timeout=wait, return_when="FIRST_COMPLETED")

                if getter in done:

                    item, getter = getter.result(), None

                    if item is END: return

                    yield Sse.pack(cast(Packet, item))

                elif producer in done and queue.empty(): return
                elif not done: yield Sse.comment()

        finally:

            for pending in (getter, producer):
                if pending is not None and not pending.done(): pending.cancel()

            with contextlib.suppress(asyncio.CancelledError): await producer
