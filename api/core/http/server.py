from granian import Granian
from granian.constants import Interfaces
from granian.log import LogLevels


class Server:

    def run (
        self, target: str, host: str = "127.0.0.1", port: int = 8000,
        workers: int = 1, reload: bool = False, level: str = "info",
    ) -> None:

        Granian(
            target, address=host, port=port, interface=Interfaces.ASGI, workers=workers,
            reload=reload, factory=True, log_access=False, log_level=LogLevels(level),
        ).serve()
