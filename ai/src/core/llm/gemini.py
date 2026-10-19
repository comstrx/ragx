from .capability import Capabilities
from collections.abc import AsyncIterator, Sequence
from typing import Any, override

from core.net import Client
from core.error import Code, Fault
from core.date import date
from .message import Attachment, Chunk, Message, Options, Reply, Usage
from .provider import Remote

BASE  = "https://generativelanguage.googleapis.com"
MODEL = "gemini-2.5-flash"
ROLES = { "user": "user", "assistant": "model" }

class Gemini(Remote):

    capabilities = Capabilities(json=True, image=True, audio=True, video=True, pdf=True, schema=True)

    name  = "gemini"
    model = MODEL

    def __init__ (
        self, key: str, model: str = MODEL, base: str = BASE, wait: float = 60.0, retries: int = 0,
        client: Client | None = None,
    ) -> None:

        super().__init__(base, key, model, wait, retries, client)

    @override
    def headers ( self ) -> dict[str, str]:

        return { "x-goog-api-key": self._key }

    def part ( self, attachment: Attachment ) -> dict[str, Any]:

        if attachment.is_text(): return { "text": f"[{attachment.name}]\n{attachment.plain()}" }

        return { "inline_data": { "mime_type": attachment.mime, "data": attachment.base64() } }

    def content ( self, message: Message ) -> dict[str, Any]:

        parts: list[dict[str, Any]] = [{ "text": message.content }] if message.content else []

        parts.extend(self.part(item) for item in message.attachments)

        return { "role": ROLES.get(message.role, "user"), "parts": parts }

    def body ( self, messages: Sequence[Message], options: Options ) -> dict[str, Any]:

        system  = options.system or next((message.content for message in messages if message.role == "system"), None)
        turns   = [message for message in messages if message.role != "system"]
        config: dict[str, Any] = {}
        payload: dict[str, Any] = { "contents": [self.content(message) for message in turns] }

        if options.temperature is not None: config["temperature"] = options.temperature
        if options.max_tokens is not None: config["maxOutputTokens"] = options.max_tokens
        if options.top_p is not None: config["topP"] = options.top_p
        if options.stop: config["stopSequences"] = list(options.stop)
        if options.json: config["responseMimeType"] = "application/json"
        if options.schema is not None and options.native_schema: config["responseJsonSchema"] = options.schema.dump()
        if system: payload["system_instruction"] = { "parts": [{ "text": system }] }
        if config: payload["generationConfig"] = config

        return payload

    def path ( self, options: Options, action: str ) -> str:

        return f"/v1beta/models/{self.pick(options)}:{action}"

    def text_of ( self, data: Any ) -> str:

        candidates = data.get("candidates") if isinstance(data, dict) else None
        first      = candidates[0] if isinstance(candidates, list) and candidates else {}
        parts      = (first.get("content") or {}).get("parts") or [] if isinstance(first, dict) else []

        return "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))

    def finish_of ( self, data: Any ) -> str | None:

        candidates = data.get("candidates") if isinstance(data, dict) else None
        first      = candidates[0] if isinstance(candidates, list) and candidates else {}

        return first.get("finishReason") if isinstance(first, dict) else None

    def usage_of ( self, data: Any ) -> Usage:

        usage = data.get("usageMetadata") if isinstance(data, dict) else None

        if not isinstance(usage, dict): return Usage()

        return Usage(int(usage.get("promptTokenCount", 0) or 0), int(usage.get("candidatesTokenCount", 0) or 0))

    async def complete ( self, messages: Sequence[Message], options: Options ) -> Reply:

        started = date.tick()
        data    = await self.post(self.path(options, "generateContent"), self.body(messages, options))

        if not isinstance(data, dict) or not isinstance(data.get("candidates"), list) or not data["candidates"]:
            raise Fault(Code.UNAVAILABLE, reason="llm.response.candidates")
        return Reply(
            self.text_of(data), str(data.get("modelVersion") or self.pick(options)), self.name,
            self.usage_of(data), self.finish_of(data), date.elapsed(started), data,
        )

    async def stream ( self, messages: Sequence[Message], options: Options ) -> AsyncIterator[Chunk]:

        path = f"{self.path(options, 'streamGenerateContent')}?alt=sse"

        async for event in self.events(path, self.body(messages, options)):

            data   = event.json()
            finish = self.finish_of(data)

            yield Chunk(self.text_of(data), finish is not None, self.usage_of(data) if finish else None, data)

    @override
    async def models ( self ) -> list[str]:

        data  = await self.get("/v1beta/models")
        found = data.get("models") if isinstance(data, dict) else []

        return sorted(
            str(item.get("name", "")).removeprefix("models/") for item in found if isinstance(item, dict)
        ) if isinstance(found, list) else []
