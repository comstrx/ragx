from .capability import Capabilities
from core.net import Client
from .compatible import Compatible

BASE  = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"

class DeepSeek(Compatible):

    capabilities = Capabilities(json=True)

    name  = "deepseek"
    model = MODEL

    def __init__ (
        self, key: str, model: str = MODEL, base: str = BASE, wait: float = 60.0, retries: int = 0,
        client: Client | None = None,
    ) -> None:

        super().__init__(base, key, model, wait, retries, client)
