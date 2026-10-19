from collections import deque

from core.error import Fault
from .job import Failed, Job

KEPT = 200

class Graveyard:

    def __init__ ( self, kept: int = KEPT ) -> None:

        self._items: deque[Failed] = deque(maxlen=kept)

    def add ( self, job: Job, error: BaseException ) -> Failed:

        kind   = error.code.value if isinstance(error, Fault) else type(error).__name__
        reason = (error.reason or error.message) if isinstance(error, Fault) else str(error)
        failed = Failed(job, kind, reason[:200])

        self._items.append(failed)

        return failed

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
