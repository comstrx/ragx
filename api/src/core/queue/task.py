from collections.abc import Callable, Mapping
from typing import Any, Protocol

from .job import Job
import functools

class Owner(Protocol):

    def register ( self, name: str, handler: Callable[..., Any] ) -> str: ...

    def name_of ( self, handler: Callable[..., Any] ) -> str: ...

    async def enqueue (
        self, handler: Callable[..., Any] | str, args: tuple[Any, ...] = (), kwargs: Mapping[str, Any] | None = None,
        queue: str | None = None, delay: float = 0.0, tries: int | None = None, backoff: float | None = None,
        unique: str | None = None,
    ) -> Job: ...

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
