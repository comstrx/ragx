from collections.abc import Callable, Mapping, Sequence
from typing import Any

from core.cache import cache
from .job import Job, Owner
import functools, inspect

type Step = tuple[Any, ...] | Callable[..., Any]
type Listed = list[list[Any]]

PAIR   = 2
PREFIX = "queue:unique:"

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

class Task[**P, T]:

    def __init__ ( self, owner: Owner, fn: Callable[P, T], queue: str | None = None, delay: float = 0.0 ) -> None:

        self._owner = owner
        self._fn    = fn
        self._queue = queue
        self._delay = delay
        self.name   = owner.register(owner.name_of(fn), fn)

        functools.update_wrapper(self, fn)

    def __call__ ( self, *args: P.args, **kwargs: P.kwargs ) -> T:

        return self._fn(*args, **kwargs)

    def on ( self, queue: str ) -> Task[P, T]:

        return Task(self._owner, self._fn, queue, self._delay)

    def delayed ( self, seconds: float ) -> Task[P, T]:

        return Task(self._owner, self._fn, self._queue, seconds)

    async def later ( self, *args: P.args, **kwargs: P.kwargs ) -> Job:

        return await self._owner.enqueue(self.name, args, kwargs, queue=self._queue, delay=self._delay)

    async def after ( self, delay: float, *args: P.args, **kwargs: P.kwargs ) -> Job:

        return await self._owner.enqueue(self.name, args, kwargs, queue=self._queue, delay=delay)

class Unique:

    def __init__ ( self ) -> None:

        self.skipped = 0

    async def claim ( self, key: str, ttl: float ) -> bool:

        return await cache.add(f"{PREFIX}{key}", 1, ttl)

    async def release ( self, key: str ) -> bool:

        return await cache.forget(f"{PREFIX}{key}")

    async def held ( self, key: str ) -> bool:

        return await cache.has(f"{PREFIX}{key}")

    async def push (
        self, owner: Owner, key: str, handler: Callable[..., Any] | str, args: tuple[Any, ...],
        kwargs: Mapping[str, Any], unique_for: float, queue: str | None, delay: float,
    ) -> Job | None:

        if not await self.claim(key, unique_for):

            self.skipped += 1

            return None

        return await owner.enqueue(handler, args, kwargs, queue=queue, delay=delay, unique=key)
