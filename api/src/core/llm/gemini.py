from collections.abc import AsyncGenerator, Sequence
from typing import Any, ClassVar, override

from core.date import date
from core.net import Transport
from .embedding import Embeddings, embeddings
from .message import Attachment, Chunk, Message, Options, Reply, Usage
from .provider import AUDIO, CORE, DOCUMENTS, EMBED, IMAGES, INSTRUCT, JSON, SCHEMA, VECTORS, VIDEO, Provider
import contextlib

BASE  = "https://generativelanguage.googleapis.com"
MODEL = "gemini-2.5-flash"
ROLES = { "user": "user", "assistant": "model" }
TASKS = { True: "RETRIEVAL_QUERY", False: "RETRIEVAL_DOCUMENT" }

class Gemini(Provider):

    name         = "gemini"
    model        = MODEL
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON, SCHEMA, IMAGES, DOCUMENTS, AUDIO, VIDEO}

    def __init__ (
        self, key: str, model: str | None = None, base: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: Transport | None = None,
    ) -> None:

        self.missing(("key", key))

        super().__init__(base or BASE, key, model, wait, retries, transport)

    @override
    def abilities ( self ) -> frozenset[str]:

        return VECTORS if "embedding" in self.model else super().abilities()

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
        if options.schema is not None and options.native:
            config["responseMimeType"]   = "application/json"
            config["responseJsonSchema"] = self.shaped(options.schema)
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

    @override
    async def answer ( self, messages: Sequence[Message], options: Options ) -> Reply:

        started = date.tick()
        data    = await self.post(self.path(options, "generateContent"), self.body(messages, options))

        return Reply(
            self.text_of(data), str(data.get("modelVersion") or self.pick(options)), self.name,
            self.usage_of(data), self.finish_of(data), date.elapsed(started), data,
        )

    @override
    async def chunks ( self, messages: Sequence[Message], options: Options ) -> AsyncGenerator[Chunk]:

        path = f"{self.path(options, 'streamGenerateContent')}?alt=sse"

        async with contextlib.aclosing(self.flow(path, self.body(messages, options))) as events:

            async for event in events:

                data   = event.json()
                finish = self.finish_of(data)

                yield Chunk(self.text_of(data), finish is not None, self.usage_of(data) if finish else None, data)

    @override
    async def vectors ( self, texts: Sequence[str], query: bool, instruction: str | None ) -> Embeddings:

        if instruction is not None: self.require(INSTRUCT)

        named = f"models/{self.model}"
        asked = [
            { "model": named, "content": { "parts": [{ "text": text }] }, "taskType": TASKS[query] } for text in texts
        ]
        data  = await self.post(f"/v1beta/{named}:batchEmbedContents", { "requests": asked }, EMBED)
        rows  = data.get("embeddings") if isinstance(data, dict) else None
        pairs = [(index, row.get("values")) for index, row in enumerate(rows or []) if isinstance(row, dict)]

        return embeddings(pairs, len(texts), self.model, self.name)

    @override
    async def models ( self ) -> list[str]:

        data  = await self.listing("/v1beta/models")
        found = data.get("models") if isinstance(data, dict) else []

        return sorted(
            str(item.get("name", "")).removeprefix("models/") for item in found if isinstance(item, dict)
        ) if isinstance(found, list) else []
