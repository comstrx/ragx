from httpx import AsyncBaseTransport
from .compatible import Compatible

PATH  = "http://127.0.0.1:11434/v1"
MODEL = "llama3.2"

class Local(Compatible):

    name  = "local"
    model = MODEL

    def __init__ (
        self, path: str = PATH, model: str = MODEL, key: str = "", wait: float = 120.0, retries: int = 0,
        transport: AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(path, key, model, wait, retries, transport)

    def path ( self ) -> str:
        return self._base
