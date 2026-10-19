from .capability import Capabilities
from .embedding import EmbeddingOptions, Embeddings, Score, scores
from core.error import Code, Fault
from collections.abc import AsyncIterator, Sequence
from typing import Any, override

from core.date import date
from .message import Attachment, Chunk, Message, Options, Reply, Usage, conversation
from .provider import Remote, text_of

DONE = "[DONE]"

class Compatible(Remote):

    name = "compatible"
    capabilities = Capabilities(json=True)

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
        if options.schema is not None and options.native_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": options.schema.dump()},
            }
        if stream: payload["stream"] = True
        if stream: payload["stream_options"] = { "include_usage": True }

        return payload

    def usage_of ( self, data: Any ) -> Usage:

        usage = data.get("usage") if isinstance(data, dict) else None

        if not isinstance(usage, dict): return Usage()

        return Usage(int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0))

    async def complete ( self, messages: Sequence[Message], options: Options ) -> Reply:

        started = date.tick()
        data    = await self.post("/chat/completions", self.body(messages, options))
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise Fault(Code.UNAVAILABLE, reason="llm.response.choices")
        first   = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        if not isinstance(message, dict): raise Fault(Code.UNAVAILABLE, reason="llm.response.message")

        return Reply(
            text_of(message.get("content")), str(data.get("model") or self.pick(options)), self.name,
            self.usage_of(data), first.get("finish_reason"), date.elapsed(started), data,
        )

    async def stream ( self, messages: Sequence[Message], options: Options ) -> AsyncIterator[Chunk]:

        async for event in self.events("/chat/completions", self.body(messages, options, stream=True)):

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
    async def embed ( self, texts: Sequence[str], options: EmbeddingOptions ) -> Embeddings:

        self.capabilities.require("embed")
        if options.instruction: raise Fault(Code.VALIDATION, reason="llm.unsupported.embedding_instruction")
        data = await self.post("/embeddings", {"model": self.model, "input": list(texts)})
        return Embeddings.parse(data, len(texts), self.model, self.name)

    @override
    async def rank ( self, query: str, documents: Sequence[str] ) -> tuple[Score, ...]:

        self.capabilities.require("rank")
        data = await self.post("/rerank", {"model": self.model, "query": query, "documents": list(documents)})
        return scores(data, documents)

    @override
    async def models ( self ) -> list[str]:

        data  = await self.get("/models")
        found = data.get("data") if isinstance(data, dict) else data

        if not isinstance(found, list): return []

        return sorted(str(item.get("id")) for item in found if isinstance(item, dict))
