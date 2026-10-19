from pathlib import Path
from typing import Any
from contextlib import AbstractAsyncContextManager
from core.json import json
from .artifact import Artifacts
from .file import File
import hashlib

class Records:

    def __init__ ( self, root: str ) -> None:

        self._root = Path(root).expanduser().resolve()
        self._files = File()
        self._locks = Artifacts(self._root)

    def path ( self, key: str ) -> Path:

        return self._root / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def lock ( self, key: str ) -> AbstractAsyncContextManager[None]:

        return self._locks.lock(key)

    async def read ( self, key: str ) -> dict[str, Any] | None:

        path = self.path(key)
        if not await self._files.exists(path): return None
        return dict(json.loads(await self._files.read_bytes(path)))

    async def write ( self, key: str, value: dict[str, Any] ) -> None:

        await self._files.write_bytes(self.path(key), json.encode(value))

    async def forget ( self, key: str ) -> bool:

        return await self._files.remove(self.path(key))
