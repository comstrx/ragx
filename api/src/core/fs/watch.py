from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.log import log
from .path import Pathish
import asyncio, os

type Snapshot = dict[str, tuple[float, int]]
type Handler = Callable[["Change"], Any]

@dataclass(frozen=True, slots=True)
class Change:

    kind : str
    path : Path

    def dump ( self ) -> dict[str, str]:

        return { "kind": self.kind, "path": str(self.path) }

class Watch:

    def __init__ ( self, target: Pathish, every: float = 0.5, recursive: bool = True, hidden: bool = False ) -> None:

        self._target    = Path(target)
        self._every     = every
        self._recursive = recursive
        self._hidden    = hidden
        self._stopping  = asyncio.Event()
        self._last: Snapshot | None = None

    def stop ( self ) -> None:

        self._stopping.set()

    def snapshot ( self ) -> Snapshot:

        seen: Snapshot = {}

        if self._target.is_file():

            stat = self._target.stat()

            return { str(self._target): (stat.st_mtime, stat.st_size) }

        if not self._target.is_dir(): return seen

        stack = [self._target]

        while stack:

            folder = stack.pop()

            try: entries = list(os.scandir(folder))
            except OSError: continue

            for entry in entries:

                if not self._hidden and entry.name.startswith("."): continue

                if entry.is_dir(follow_symlinks=False):

                    if self._recursive: stack.append(Path(entry.path))

                    continue

                try: stat = entry.stat(follow_symlinks=False)
                except OSError: continue

                seen[entry.path] = (stat.st_mtime, stat.st_size)

        return seen

    def compare ( self, before: Snapshot, after: Snapshot ) -> list[Change]:

        changes = [Change("created", Path(path)) for path in after if path not in before]

        changes.extend(Change("deleted", Path(path)) for path in before if path not in after)
        changes.extend(
            Change("modified", Path(path)) for path, mark in after.items() if path in before and before[path] != mark
        )

        return sorted(changes, key=lambda change: (change.kind, str(change.path)))

    async def changes ( self ) -> AsyncIterator[Change]:

        self._stopping.clear()
        self._last = await asyncio.to_thread(self.snapshot)

        while not self._stopping.is_set():

            try:
                async with asyncio.timeout(self._every): await self._stopping.wait()
            except TimeoutError: pass

            if self._stopping.is_set(): break

            current = await asyncio.to_thread(self.snapshot)

            for change in self.compare(self._last, current): yield change

            self._last = current

    async def once ( self, within: float = 30.0 ) -> Change | None:

        try:

            async with asyncio.timeout(within):

                async for change in self.changes():

                    self.stop()

                    return change

        except TimeoutError: return None

        return None

    async def run ( self, handler: Handler ) -> int:

        count = 0

        async for change in self.changes():

            count += 1

            try:

                result = handler(change)

                if asyncio.iscoroutine(result): await result

            except Exception:

                log.exception("watch.handler_failed", path=str(change.path), kind=change.kind)

        return count
