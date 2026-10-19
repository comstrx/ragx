from collections.abc import Mapping, Sequence
from core.error import Code, Fault
from contextlib import suppress
import asyncio, os, signal

class Process:

    def __init__ ( self, child: asyncio.subprocess.Process, log_limit: int = 65536 ) -> None:

        self._child = child
        self._limit = log_limit
        self._log = bytearray()
        self._reader = asyncio.create_task(self._drain())
        self._writer: asyncio.Task[None] | None = None

    @classmethod
    async def start ( cls, command: Sequence[str], environment: Mapping[str, str] | None = None,
        log_limit: int = 65536, input_data: bytes | None = None, inherit: bool = True,
    ) -> Process:

        child = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
            env={**(os.environ if inherit else {"LANG": "C.UTF-8"}), **(environment or {})}, start_new_session=True,
        )

        process = cls(child, log_limit)
        if input_data is not None: process._writer = asyncio.create_task(process._feed(input_data))
        return process

    async def _feed ( self, data: bytes ) -> None:

        if self._child.stdin is None: return
        try:
            self._child.stdin.write(data)
            await self._child.stdin.drain()
        except (BrokenPipeError, ConnectionResetError): pass
        finally: self._child.stdin.close()

    async def _drain ( self ) -> None:

        if self._child.stdout is None: return

        while block := await self._child.stdout.read(8192):
            self._log.extend(block)
            if len(self._log) > self._limit: del self._log[:-self._limit]

    def running ( self ) -> bool:

        return self._child.returncode is None

    def output ( self ) -> str:

        return self._log.decode(errors="replace")

    async def wait ( self, seconds: float = 60.0 ) -> int:

        try:
            async with asyncio.timeout(seconds):
                code = await self._child.wait()
                await self._reader
                return code
        except TimeoutError as error:
            await self.close()
            raise Fault(Code.UNAVAILABLE, reason="process.timeout") from error

    async def close ( self, grace: float = 3.0 ) -> None:

        if self.running():
            with suppress(ProcessLookupError): os.killpg(self._child.pid, signal.SIGTERM)
            try:
                async with asyncio.timeout(grace): await self._child.wait()
            except TimeoutError:
                with suppress(ProcessLookupError): os.killpg(self._child.pid, signal.SIGKILL)
                await self._child.wait()
        await self._reader
        if self._writer is not None: await self._writer
