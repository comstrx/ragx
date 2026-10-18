from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Self

from core.date import date

DEFAULT = "default"
TRIES   = 3
BACKOFF = 1.0

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
            "unique": self.unique,
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any], receipt: Any = None ) -> Job:

        return cls(
            str(data["id"]), str(data["name"]), tuple(data.get("args", ())), dict(data.get("kwargs", {})),
            str(data.get("queue", DEFAULT)), int(data.get("tries", TRIES)), float(data.get("backoff", BACKOFF)),
            int(data.get("attempts", 0)), float(data.get("available", 0.0)), data.get("unique"), receipt,
        )

@dataclass(frozen=True, slots=True)
class Failed:

    job    : Job
    error  : str
    reason : str
    at     : float = field(default_factory=date.stamp)

    def dump ( self ) -> dict[str, Any]:
        return { **self.job.dump(), "error": self.error, "reason": self.reason, "failed_at": self.at }

class Queued:

    queue   : str = DEFAULT
    delay   : float = 0.0
    tries   : int = TRIES
    backoff : float = BACKOFF
