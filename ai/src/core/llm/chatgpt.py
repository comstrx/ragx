from .capability import Capabilities
from core.net import Client
from collections.abc import Sequence
from typing import Any, override
from .message import Message, Options
from .compatible import Compatible

BASE  = "https://api.openai.com/v1"
MODEL = "gpt-5"

class ChatGpt(Compatible):

    capabilities = Capabilities(json=True, image=True, schema=True)

    name  = "chatgpt"
    model = MODEL

    def __init__ (
        self, key: str, model: str = MODEL, base: str = BASE, wait: float = 60.0, retries: int = 0,
        client: Client | None = None,
    ) -> None:

        super().__init__(base, key, model, wait, retries, client)
        if model.startswith("text-embedding-"):
            self.capabilities = Capabilities(generate=False, stream=False, embed=True)

    @override
    def body ( self, messages: Sequence[Message], options: Options, stream: bool = False ) -> dict[str, Any]:

        payload = super().body(messages, options, stream)
        if "max_tokens" in payload: payload["max_completion_tokens"] = payload.pop("max_tokens")
        return payload
