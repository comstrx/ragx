from collections.abc import Callable, Sequence
from typing import Any

from .job import Job, Owner
import inspect

type Step = tuple[Any, ...] | Callable[..., Any]
type Listed = list[list[Any]]

PAIR = 2

class Flow:

    def __init__ ( self, owner: Owner ) -> None:

        self._owner = owner
        self._name  = owner.register(owner.name_of(self.run), self.run)

    def normalize ( self, steps: Sequence[Step] ) -> Listed:

        listed: Listed = []

        for step in steps:

            parts  = (step,) if callable(step) else tuple(step)
            fn     = parts[0]
            args   = list(parts[1]) if len(parts) >= PAIR else []
            kwargs = dict(parts[2]) if len(parts) > PAIR else {}

            listed.append([self._owner.register(self._owner.name_of(fn), fn), args, kwargs])

        return listed

    async def chain ( self, steps: Sequence[Step], queue: str | None = None, delay: float = 0.0 ) -> Job:

        return await self._owner.enqueue(self._name, (self.normalize(steps),), queue=queue, delay=delay)

    async def batch ( self, steps: Sequence[Step], queue: str | None = None, delay: float = 0.0 ) -> list[Job]:

        jobs: list[Job] = []

        for name, args, kwargs in self.normalize(steps):
            jobs.append(await self._owner.enqueue(name, tuple(args), kwargs, queue=queue, delay=delay))

        return jobs

    async def run ( self, steps: Listed ) -> int:

        done = 0

        for name, args, kwargs in steps:

            result = self._owner.handler(name)(*args, **kwargs)

            if inspect.isawaitable(result): await result

            done += 1

        return done
