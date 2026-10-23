from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol, Self, TypedDict, Unpack

from engine.date import date
from engine.error import Fault
import inspect

DEFAULT = "default"
TRIES   = 3
BACKOFF = 1.0
KEPT    = 200

type Failure = Callable[[Job, BaseException], Awaitable[None] | None]
type Success = Callable[[Job], Awaitable[None] | None]

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
    unique    : str | None = None
    context   : dict[str, Any] = field(default_factory=dict)
    timeout   : float = 0.0
    receipt   : Any = field(default=None, compare=False, repr=False)

    def again ( self, delay: float ) -> Self:

        return replace(self, attempts=self.attempts + 1, available=date.stamp() + delay, receipt=None)

    def fresh ( self ) -> Self:

        return replace(self, attempts=0, available=date.stamp(), receipt=None)

    def exhausted ( self ) -> bool:

        return self.attempts + 1 >= self.tries

    def delay ( self ) -> float:

        return max(self.available - date.stamp(), 0.0)

    def short ( self ) -> str:

        return self.name.rsplit(".", 1)[-1].rsplit(":", 1)[-1]

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "name": self.name, "args": list(self.args), "kwargs": self.kwargs, "queue": self.queue,
            "tries": self.tries, "backoff": self.backoff, "attempts": self.attempts, "available": self.available,
            "unique": self.unique, "context": self.context, "timeout": self.timeout,
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any], receipt: Any = None ) -> Job:

        return cls(
            str(data["id"]), str(data["name"]), tuple(data.get("args", ())), dict(data.get("kwargs", {})),
            str(data.get("queue", DEFAULT)), int(data.get("tries", TRIES)), float(data.get("backoff", BACKOFF)),
            int(data.get("attempts", 0)), float(data.get("available", 0.0)), data.get("unique"),
            dict(data.get("context") or {}), float(data.get("timeout") or 0.0), receipt,
        )

@dataclass(frozen=True, slots=True)
class Failed:

    job    : Job
    error  : str
    reason : str
    at     : float = field(default_factory=date.stamp)

    def dump ( self ) -> dict[str, Any]:

        return { **self.job.dump(), "error": self.error, "reason": self.reason, "failed_at": self.at }

class Dispatch(TypedDict, total=False):

    queue   : str | None
    delay   : float
    tries   : int | None
    backoff : float | None
    unique  : str | None
    timeout : float | None

class Queued:

    queue   : str = DEFAULT
    delay   : float = 0.0
    tries   : int = TRIES
    backoff : float = BACKOFF
    timeout : float = 0.0

class Owner(Protocol):

    def register ( self, name: str, handler: Callable[..., Any] ) -> str: ...

    def name_of ( self, handler: Callable[..., Any] ) -> str: ...

    def handler ( self, name: str ) -> Callable[..., Any]: ...

    async def enqueue (
        self, handler: Callable[..., Any] | str, args: tuple[Any, ...] = (), kwargs: Mapping[str, Any] | None = None,
        **options: Unpack[Dispatch],
    ) -> Job: ...

class Graveyard:

    def __init__ ( self, kept: int = KEPT ) -> None:

        self._items: deque[Failed] = deque(maxlen=kept)
        self._failed: Failure | None = None
        self._succeeded: Success | None = None

    def add ( self, job: Job, error: BaseException ) -> Failed:

        kind   = error.code.value if isinstance(error, Fault) else type(error).__name__
        reason = (error.reason or error.message) if isinstance(error, Fault) else str(error)
        failed = Failed(job, kind, reason[:200])

        self._items.append(failed)

        return failed

    def on_failure ( self, handler: Failure ) -> None:

        self._failed = handler

    def on_success ( self, handler: Success ) -> None:

        self._succeeded = handler

    async def bury ( self, job: Job, error: BaseException ) -> None:

        self.add(job, error)

        if self._failed is None: return

        outcome = self._failed(job, error)

        if inspect.isawaitable(outcome): await outcome

    async def celebrate ( self, job: Job ) -> None:

        if self._succeeded is None: return

        outcome = self._succeeded(job)

        if inspect.isawaitable(outcome): await outcome

    def failed ( self, limit: int = 50 ) -> list[Failed]:

        return list(self._items)[-limit:]

    def take ( self, job_id: str | None = None ) -> list[Failed]:

        chosen = [failed for failed in self._items if job_id is None or failed.job.id == job_id]

        for failed in chosen: self._items.remove(failed)

        return chosen

    def flush ( self ) -> int:

        count = len(self._items)

        self._items.clear()

        return count

    def __len__ ( self ) -> int:

        return len(self._items)
