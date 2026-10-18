from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from core.date import date
from core.error import Code, Fault
from core.json import json
from core.log import log
from core.rand import rand
from .driver import Driver
from .flow import Flow, Step
from .graveyard import Graveyard
from .job import BACKOFF, DEFAULT, TRIES, Failed, Job
from .task import Task
from .unique import Unique
from .worker import Workers
import inspect

type Handler = Callable[..., Any]
type Failure = Callable[[Job, BaseException], Awaitable[None] | None]
type Success = Callable[[Job], Awaitable[None] | None]

class Queue:

    def __init__ ( self ) -> None:

        self._driver: Driver | None = None
        self._handlers: dict[str, Handler] = {}
        self._queues: tuple[str, ...] = (DEFAULT,)
        self._tries   = TRIES
        self._backoff = BACKOFF
        self._failed: Failure | None = None
        self._succeeded: Success | None = None
        self._graveyard = Graveyard()
        self._workers   = Workers(self.pull, self.perform)
        self._flow      = Flow(self)
        self._unique    = Unique()
        self._processed = 0
        self._failures  = 0

    def setup (
        self, driver: Driver, queues: Sequence[str] = (DEFAULT,), tries: int = TRIES, backoff: float = BACKOFF,
    ) -> None:

        self._driver  = driver
        self._queues  = tuple(queues) or (DEFAULT,)
        self._tries   = tries
        self._backoff = backoff

    def ready ( self ) -> bool:
        return self._driver is not None

    def driver ( self ) -> Driver:

        if self._driver is None: raise Fault(Code.INTERNAL, reason="queue")

        return self._driver

    def inline ( self ) -> bool:
        return self._driver is None or self._driver.name == "sync"

    def queues ( self ) -> tuple[str, ...]:
        return self._queues

    def on_failure ( self, handler: Failure ) -> None:
        self._failed = handler

    def on_success ( self, handler: Success ) -> None:
        self._succeeded = handler

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
        unique: str | None = None,
    ) -> Job:

        name = handler if isinstance(handler, str) else self.register(self.name_of(handler), handler)
        job  = Job(
            str(rand.uuid()), name, tuple(json.loads(json.encode(args))), json.loads(json.encode(dict(kwargs or {}))),
            queue or self._queues[0], tries or self._tries, backoff if backoff is not None else self._backoff,
            0, date.stamp() + max(delay, 0.0), unique,
        )

        self.handler(name)

        if self.inline(): await self.perform(job)
        else: await self.driver().push(job)

        return job

    async def push_unique (
        self, key: str, handler: Handler | str, *args: Any, unique_for: float = 60.0, queue: str | None = None,
        delay: float = 0.0, **kwargs: Any,
    ) -> Job | None:
        return await self._unique.push(self, key, handler, args, kwargs, unique_for, queue, delay)

    async def bulk ( self, handler: Handler | str, items: Sequence[tuple[Any, ...]], queue: str | None = None ) -> int:

        for args in items: await self.enqueue(handler, tuple(args), queue=queue)

        return len(items)

    async def chain ( self, steps: Sequence[Step], queue: str | None = None, delay: float = 0.0 ) -> Job:
        return await self._flow.chain(steps, queue, delay)

    async def batch ( self, steps: Sequence[Step], queue: str | None = None, delay: float = 0.0 ) -> list[Job]:
        return await self._flow.batch(steps, queue, delay)

    async def pull ( self, queue: str, wait: float ) -> Job | None:
        return await self.driver().pull(queue, wait)

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
                await self.settle(job)

                if job.unique: await self._unique.release(job.unique)

                return False

            retry = job.again(job.backoff * (2 ** job.attempts))

            log.warning("queue.retry", job=job.name, id=job.id, attempt=retry.attempts, error=type(error).__name__)

            await self.driver().push(retry)
            await self.settle(job)

            return False

        self._processed += 1

        await self.settle(job)
        await self.celebrate(job)

        if job.unique: await self._unique.release(job.unique)

        return True

    async def settle ( self, job: Job ) -> None:

        if self._driver is not None and job.receipt is not None: await self._driver.ack(job)

    async def bury ( self, job: Job, error: BaseException ) -> None:

        self._graveyard.add(job, error)

        if self._failed is None: return

        outcome = self._failed(job, error)

        if inspect.isawaitable(outcome): await outcome

    async def celebrate ( self, job: Job ) -> None:

        if self._succeeded is None: return

        outcome = self._succeeded(job)

        if inspect.isawaitable(outcome): await outcome

    def failed ( self, limit: int = 50 ) -> list[Failed]:
        return self._graveyard.failed(limit)

    async def retry_failed ( self, job_id: str | None = None ) -> int:

        chosen = self._graveyard.take(job_id)

        for failed in chosen: await self.driver().push(failed.job.fresh())

        return len(chosen)

    def flush_failed ( self ) -> int:
        return self._graveyard.flush()

    def start ( self, workers: int = 1 ) -> int:

        if self.inline(): return 0

        started = self._workers.start(self._queues, workers)

        if started: log.info("queue.started", driver=self.driver().name, queues=list(self._queues), workers=started)

        return started

    async def stop ( self, wait: float = 5.0 ) -> int:

        stopped = await self._workers.stop(wait)

        if stopped: log.info("queue.stopped", processed=self._processed, failures=self._failures)

        return stopped

    def pause ( self ) -> bool:
        return self._workers.pause()

    def resume ( self ) -> bool:
        return self._workers.resume()

    def paused ( self ) -> bool:
        return self._workers.paused()

    async def close ( self ) -> None:

        await self.stop()

        if self._driver is not None: await self._driver.close()

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

    async def sizes ( self ) -> dict[str, int]:
        return { name: await self.driver().size(name) for name in self._queues }

    async def clear ( self, queue: str | None = None ) -> int:
        return await self.driver().clear(queue or self._queues[0])

    async def clear_all ( self ) -> int:
        return sum([await self.driver().clear(name) for name in self._queues])

    def stats ( self ) -> Mapping[str, int]:

        return {
            "processed": self._processed, "failures": self._failures, "workers": self._workers.alive(),
            "buried": len(self._graveyard), "skipped": self._unique.skipped,
        }

    def describe ( self ) -> dict[str, object]:

        return {
            "driver": self._driver.name if self._driver else None, "queues": list(self._queues),
            "handlers": len(self._handlers), **self.stats(), **self._workers.describe(),
        }
