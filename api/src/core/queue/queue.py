from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, Self

from core.date import date
from core.exceptions import Code, Fault
from core.json import json
from core.log import log
from core.rand import rand
import asyncio, functools, inspect

type Handler = Callable[..., Any]
type Failure = Callable[["Job", BaseException], Awaitable[None] | None]

DEFAULT = "default"
TRIES   = 3
BACKOFF = 1.0
PULL    = 0.5

@dataclass(frozen=True, slots=True)
class Job:

    id        : str
    name      : str
    args      : tuple[Any, ...] = ()
    kwargs    : dict[str, Any] = field(default_factory=dict)
    queue     : str = DEFAULT
    tries     : int = TRIES
    backoff   : float = BACKOFF
    attempts  : int = 0
    available : float = 0.0

    def again ( self, delay: float ) -> Self:
        return replace(self, attempts=self.attempts + 1, available=date.stamp() + delay)

    def exhausted ( self ) -> bool:
        return self.attempts + 1 >= self.tries

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "name": self.name, "args": list(self.args), "kwargs": self.kwargs, "queue": self.queue,
            "tries": self.tries, "backoff": self.backoff, "attempts": self.attempts, "available": self.available,
        }

class Driver(Protocol):

    @property
    def name ( self ) -> str: ...

    async def push ( self, job: Job ) -> None: ...

    async def pull ( self, queue: str, wait: float ) -> Job | None: ...

    async def size ( self, queue: str ) -> int: ...

    async def clear ( self, queue: str ) -> int: ...

class Queued:

    queue   : str = DEFAULT
    delay   : float = 0.0
    tries   : int = TRIES
    backoff : float = BACKOFF

class Queue:

    def __init__ ( self ) -> None:

        self._driver: Driver | None = None
        self._handlers: dict[str, Handler] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._queues: tuple[str, ...] = (DEFAULT,)
        self._tries   = TRIES
        self._backoff = BACKOFF
        self._failed: Failure | None = None
        self._stopping = asyncio.Event()
        self._processed = 0
        self._failures  = 0

    def setup (
        self, driver: Driver, queues: tuple[str, ...] = (DEFAULT,), tries: int = TRIES, backoff: float = BACKOFF,
    ) -> None:

        self._driver  = driver
        self._queues  = queues or (DEFAULT,)
        self._tries   = tries
        self._backoff = backoff

    def ready ( self ) -> bool:
        return self._driver is not None

    def driver ( self ) -> Driver:

        if self._driver is None: raise Fault(Code.INTERNAL, reason="queue")

        return self._driver

    def inline ( self ) -> bool:
        return self._driver is None or self._driver.name == "sync"

    def on_failure ( self, handler: Failure ) -> None:
        self._failed = handler

    def register ( self, name: str, handler: Handler ) -> str:

        self._handlers[name] = handler

        return name

    def name_of ( self, handler: Handler ) -> str:
        return f"{handler.__module__}:{handler.__qualname__}"

    def handler ( self, name: str ) -> Handler:

        found = self._handlers.get(name)

        if found is None: raise Fault(Code.INTERNAL, reason=f"queue.{name}")

        return found

    def names ( self ) -> list[str]:
        return sorted(self._handlers)

    def task[**P, T] ( self, fn: Callable[P, T] ) -> Task[P, T]:
        return Task(self, fn)

    async def push (
        self, handler: Handler | str, *args: Any, queue: str | None = None, delay: float = 0.0,
        tries: int | None = None, backoff: float | None = None, **kwargs: Any,
    ) -> Job:
        return await self.enqueue(handler, args, kwargs, queue=queue, delay=delay, tries=tries, backoff=backoff)

    async def enqueue (
        self, handler: Handler | str, args: tuple[Any, ...] = (), kwargs: Mapping[str, Any] | None = None,
        queue: str | None = None, delay: float = 0.0, tries: int | None = None, backoff: float | None = None,
    ) -> Job:

        name = handler if isinstance(handler, str) else self.register(self.name_of(handler), handler)
        job  = Job(
            str(rand.uuid()), name, tuple(json.loads(json.encode(args))), json.loads(json.encode(dict(kwargs or {}))),
            queue or self._queues[0], tries or self._tries, backoff if backoff is not None else self._backoff,
            0, date.stamp() + max(delay, 0.0),
        )

        self.handler(name)

        if self.inline(): await self.perform(job)
        else: await self.driver().push(job)

        return job

    async def perform ( self, job: Job ) -> bool:

        fn = self.handler(job.name)

        try:

            result = fn(*job.args, **job.kwargs)

            if inspect.isawaitable(result): await result

        except Exception as error:

            self._failures += 1

            if job.exhausted():

                log.exception("queue.failed", job=job.name, id=job.id, attempts=job.attempts + 1)

                await self.bury(job, error)

                return False

            retry = job.again(job.backoff * (2 ** job.attempts))

            log.warning("queue.retry", job=job.name, id=job.id, attempt=retry.attempts, error=type(error).__name__)

            await self.driver().push(retry)

            return False

        self._processed += 1

        return True

    async def bury ( self, job: Job, error: BaseException ) -> None:

        if self._failed is None: return

        outcome = self._failed(job, error)

        if inspect.isawaitable(outcome): await outcome

    def start ( self, workers: int = 1 ) -> None:

        if self.inline() or self._workers or workers < 1: return

        self._stopping.clear()

        for queue in self._queues:
            for index in range(workers):
                self._workers.append(asyncio.create_task(self.work(queue), name=f"queue:{queue}:{index}"))

        log.info("queue.started", driver=self.driver().name, queues=list(self._queues), workers=len(self._workers))

    async def work ( self, queue: str ) -> None:

        while not self._stopping.is_set():

            job = await self.driver().pull(queue, PULL)

            if job is not None: await self.perform(job)

    async def stop ( self, wait: float = 5.0 ) -> None:

        if not self._workers: return

        self._stopping.set()

        try:
            async with asyncio.timeout(wait): await asyncio.gather(*self._workers, return_exceptions=True)
        except TimeoutError:
            for worker in self._workers: worker.cancel()

        self._workers.clear()

        log.info("queue.stopped", processed=self._processed, failures=self._failures)

    async def drain ( self, queue: str | None = None, limit: int = 10_000 ) -> int:

        if self.inline(): return 0

        done = 0

        for name in ((queue,) if queue else self._queues):

            while done < limit:

                job = await self.driver().pull(name, 0.0)

                if job is None: break

                await self.perform(job)

                done += 1

        return done

    async def size ( self, queue: str | None = None ) -> int:
        return await self.driver().size(queue or self._queues[0])

    async def clear ( self, queue: str | None = None ) -> int:
        return await self.driver().clear(queue or self._queues[0])

    def stats ( self ) -> Mapping[str, int]:
        return { "processed": self._processed, "failures": self._failures, "workers": len(self._workers) }

class Task[**P, T]:

    def __init__ ( self, owner: Queue, fn: Callable[P, T] ) -> None:

        self._owner = owner
        self._fn    = fn
        self.name   = owner.register(owner.name_of(fn), fn)

        functools.update_wrapper(self, fn)

    def __call__ ( self, *args: P.args, **kwargs: P.kwargs ) -> T:
        return self._fn(*args, **kwargs)

    async def later ( self, *args: P.args, **kwargs: P.kwargs ) -> Job:
        return await self._owner.enqueue(self.name, args, kwargs)

    async def after ( self, delay: float, *args: P.args, **kwargs: P.kwargs ) -> Job:
        return await self._owner.enqueue(self.name, args, kwargs, delay=delay)
