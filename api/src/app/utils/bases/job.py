from typing import Any

from core.log import Logger, log
from core.queue import Job, Queued, queue

class BaseJob:

    def __init__ ( self, *args: Any, **kwargs: Any ) -> None:

        self.args   = args
        self.kwargs = kwargs

    async def handle ( self ) -> None:
        return None

    @property
    def log ( self ) -> Logger:
        return log.bind(job=type(self).__name__)

    @classmethod
    def queued ( cls ) -> bool:
        return issubclass(cls, Queued) and not queue.inline()

    @classmethod
    async def perform ( cls, *args: Any, **kwargs: Any ) -> None:
        await cls(*args, **kwargs).handle()

    @classmethod
    async def dispatch ( cls, *args: Any, **kwargs: Any ) -> Job | None:

        if not cls.queued():

            await cls.perform(*args, **kwargs)

            return None

        return await queue.enqueue(
            cls.perform, args, kwargs,
            queue=getattr(cls, "queue", None), delay=getattr(cls, "delay", 0.0),
            tries=getattr(cls, "tries", None), backoff=getattr(cls, "backoff", None),
        )

    @classmethod
    async def dispatch_now ( cls, *args: Any, **kwargs: Any ) -> None:
        await cls.perform(*args, **kwargs)
