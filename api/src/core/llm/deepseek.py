from httpx import AsyncBaseTransport
from .compatible import Compatible

BASE  = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"

class DeepSeek(Compatible):

    name  = "deepseek"
    model = MODEL

    def __init__ (
        self, key: str, model: str = MODEL, base: str = BASE, wait: float = 60.0, retries: int = 1,
        transport: AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(base, key, model, wait, retries, transport)
