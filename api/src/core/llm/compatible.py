from collections.abc import AsyncGenerator, Iterable, Sequence
from typing import Any, ClassVar, override

from core.date import date
from core.net import Transport
from .embedding import Embeddings, Score, embeddings, ranked
from .message import Attachment, Chunk, Message, Options, Reply, Usage, conversation
from .provider import (
    CORE, DOCUMENTS, EMBED, IMAGES, INSTRUCT, JSON, METADATA, RANK, SCHEMA, VECTORS, Provider, text_of,
)
import contextlib

DONE     = "[DONE]"
OPENAI   = "https://api.openai.com/v1"
DEEPSEEK = "https://api.deepseek.com/v1"
OLLAMA   = "http://127.0.0.1:11434/v1"

class Compatible(Provider):

    name         = "compatible"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON}

    def part ( self, attachment: Attachment ) -> dict[str, Any]:

        if attachment.is_image(): return { "type": "image_url", "image_url": { "url": attachment.data_url() } }
        if attachment.is_text(): return { "type": "text", "text": f"[{attachment.name}]\n{attachment.plain()}" }

        return { "type": "file", "file": { "filename": attachment.name, "file_data": attachment.data_url() } }

    def content ( self, message: Message ) -> Any:

        if not message.attachments: return message.content

        parts: list[dict[str, Any]] = [{ "type": "text", "text": message.content }] if message.content else []

        return [*parts, *(self.part(item) for item in message.attachments)]

    def body ( self, messages: Sequence[Message], options: Options, stream: bool = False ) -> dict[str, Any]:

        turns = conversation(messages, options)
        payload: dict[str, Any] = {
            "model"    : self.pick(options),
            "messages" : [{ "role": message.role, "content": self.content(message) } for message in turns],
            **options.generation(),
        }

        if options.json: payload["response_format"] = { "type": "json_object" }
        if options.schema is not None and options.native:
            shaped = { "name": "output", "strict": options.schema.strict(), "schema": self.shaped(options.schema) }
            payload["response_format"] = { "type": "json_schema", "json_schema": shaped }
        if options.metadata: payload["metadata"] = dict(options.metadata)
        if stream: payload["stream"] = True
        if stream: payload["stream_options"] = { "include_usage": True }

        return payload

    def usage_of ( self, data: Any ) -> Usage:

        usage = data.get("usage") if isinstance(data, dict) else None

        if not isinstance(usage, dict): return Usage()

        return Usage(int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0))

    @override
    async def answer ( self, messages: Sequence[Message], options: Options ) -> Reply:

        started = date.tick()
        data    = await self.post("/chat/completions", self.body(messages, options))
        choices = data.get("choices") or [{}]
        first   = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") or {}

        return Reply(
            text_of(message.get("content")), str(data.get("model") or self.pick(options)), self.name,
            self.usage_of(data), first.get("finish_reason"), date.elapsed(started), data,
        )

    @override
    async def chunks ( self, messages: Sequence[Message], options: Options ) -> AsyncGenerator[Chunk]:

        flowing = self.flow("/chat/completions", self.body(messages, options, stream=True))

        async with contextlib.aclosing(flowing) as events:

            async for event in events:

                if event.data.strip() == DONE:

                    yield Chunk("", done=True)

                    return

                data    = event.json()
                choices = data.get("choices") or [] if isinstance(data, dict) else []
                first   = choices[0] if choices and isinstance(choices[0], dict) else {}
                delta   = first.get("delta") or {}
                usage   = self.usage_of(data) if isinstance(data, dict) and data.get("usage") else None

                yield Chunk(text_of(delta.get("content")), bool(first.get("finish_reason")), usage, data)

    @override
    async def vectors ( self, texts: Sequence[str], query: bool, instruction: str | None ) -> Embeddings:

        if instruction is not None: self.require(INSTRUCT)

        written = [f"Instruct: {instruction}\nQuery: {text}" for text in texts] if instruction else list(texts)
        data    = await self.post("/embeddings", { "model": self.model, "input": written }, EMBED)
        rows    = data.get("data") if isinstance(data, dict) else None
        pairs   = [(row.get("index"), row.get("embedding")) for row in rows or [] if isinstance(row, dict)]

        return embeddings(pairs, len(texts), self.model, self.name, self.usage_of(data))

    @override
    async def scores ( self, query: str, documents: Sequence[str] ) -> tuple[Score, ...]:

        data = await self.post("/rerank", { "model": self.model, "query": query, "documents": list(documents) }, RANK)

        return ranked(data.get("results") if isinstance(data, dict) else None, len(documents))

    @override
    async def models ( self ) -> list[str]:

        data  = await self.listing("/models")
        found = data.get("data") if isinstance(data, dict) else data

        if not isinstance(found, list): return []

        return sorted(str(item.get("id")) for item in found if isinstance(item, dict))

class ChatGpt(Compatible):

    name         = "chatgpt"
    model        = "gpt-5"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON, SCHEMA, IMAGES, DOCUMENTS, METADATA}

    def __init__ (
        self, key: str, model: str | None = None, base: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: Transport | None = None, name: str | None = None,
    ) -> None:

        self.missing(("key", key))

        super().__init__(base or OPENAI, key, model, wait, retries, transport, name=name)

    @override
    def abilities ( self ) -> frozenset[str]:

        return VECTORS if self.model.startswith("text-embedding-") else super().abilities()

    @override
    def body ( self, messages: Sequence[Message], options: Options, stream: bool = False ) -> dict[str, Any]:

        payload = super().body(messages, options, stream)

        if "max_tokens" in payload: payload["max_completion_tokens"] = payload.pop("max_tokens")

        return payload

class DeepSeek(Compatible):

    name         = "deepseek"
    model        = "deepseek-chat"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON}

    def __init__ (
        self, key: str, model: str | None = None, base: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: Transport | None = None,
    ) -> None:

        self.missing(("key", key))

        super().__init__(base or DEEPSEEK, key, model, wait, retries, transport)

class Local(Compatible):

    name         = "local"
    model        = "llama3.2"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON, IMAGES}

    def __init__ (
        self, path: str | None = None, model: str | None = None, key: str | None = None, wait: float = 120.0,
        retries: int = 0, transport: Transport | None = None, serves: Iterable[str] | None = None,
        name: str | None = None,
    ) -> None:

        super().__init__(path or OLLAMA, key or "", model, wait, retries, transport, serves, name)
