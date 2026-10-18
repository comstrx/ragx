from .pool import Lane, Pool
from .run import Run
from .signal import Shutdown
from .tasks import Tasks

class Thread(Run):

    def __init__ ( self ) -> None:

        self.pool     = Pool()
        self.tasks    = Tasks()
        self.shutdown = Shutdown()

    def lane ( self, name: str, limit: int = 8 ) -> Lane:
        return self.pool.lane(name, limit)

    def describe ( self ) -> dict[str, object]:

        return {
            "lanes": self.pool.describe(),
            "tasks": self.tasks.describe(),
            "shutdown": self.shutdown.triggered(),
        }
