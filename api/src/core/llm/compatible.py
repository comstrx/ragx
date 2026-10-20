from collections.abc import AsyncGenerator, Sequence
from typing import Any, ClassVar, override

from core.date import date
from core.error import Code, Fault
from .message import EFFORTS, Attachment, Chunk, Message, Options, Reply, Usage, conversation
from .provider import (
    CORE, DOCUMENTS, EMBED, HEARING, IMAGES, INSTRUCT, JSON, METADATA, RANK, SCHEMA, TOKENS, TRANSCRIBE, VECTORS,
    Provider, text_of,
)
from .result import Embeddings, Score, Transcript, embeddings, ranked, transcript
import contextlib

DONE = "[DONE]"
WIRE = {
    "temperature" : "temperature",
    "top_p"       : "top_p",
    "top_k"       : "top_k",
    "stop"        : "stop",
    "seed"        : "seed",
    "presence"    : "presence_penalty",
    "frequency"   : "frequency_penalty",
    "effort"      : "reasoning_effort",
}

class Compatible(Provider):

    name         = "compatible"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON}
    tunes        : ClassVar[frozenset[str]] = frozenset(WIRE)
    efforts      : ClassVar[frozenset[str]] = frozenset(EFFORTS)
    limit        : ClassVar[str] = "max_tokens"

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
        tuned = { WIRE[name]: list(value) if name == "stop" else value for name, value in self.tuned(options).items() }
        payload: dict[str, Any] = {
            "model"    : self.pick(options),
            "messages" : [{ "role": message.role, "content": self.content(message) } for message in turns],
            **tuned,
        }

        if options.max_tokens is not None: payload[self.limit] = options.max_tokens
        if options.json: payload["response_format"] = { "type": "json_object" }
        if options.schema is not None and options.native:
            shaped = { "name": "output", "strict": options.schema.strict(), "schema": self.shaped(options.schema) }
            payload["response_format"] = { "type": "json_schema", "json_schema": shaped }
        if options.metadata: payload["metadata"] = dict(options.metadata)
        if stream: payload["stream"] = True
        if stream: payload["stream_options"] = { "include_usage": True }

        return { **payload, **options.extra }

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
    async def tally ( self, messages: Sequence[Message], options: Options ) -> int:

        root   = self._base.removesuffix("/v1")
        turns  = self.body(messages, options)["messages"]
        shaped = await self.post(f"{root}/apply-template", { "messages": turns }, TOKENS)
        found  = await self.post(f"{root}/tokenize", { "content": str(shaped.get("prompt", "")) }, TOKENS)
        tokens = found.get("tokens") if isinstance(found, dict) else None

        if not isinstance(tokens, list): raise Fault(Code.UNAVAILABLE, reason="llm.tokens.response")

        return len(tokens)

    @override
    async def listen ( self, media: Attachment, language: str | None ) -> Transcript:

        fields = { "model": self.model, "response_format": "verbose_json", "timestamp_granularities[]": "segment" }
        sent   = { **fields, "language": language } if language else fields
        files  = { "file": (media.name, media.data, media.mime) }
        data   = await self.call("POST", "/audio/transcriptions", TRANSCRIBE, files=files, data=sent)

        return transcript(data, self.model, self.name)

    @override
    async def models ( self ) -> list[str]:

        data  = await self.listing("/models")
        found = data.get("data") if isinstance(data, dict) else data

        if not isinstance(found, list): return []

        return sorted(str(item.get("id")) for item in found if isinstance(item, dict))

class ChatGpt(Compatible):

    name         = "chatgpt"
    base         = "https://api.openai.com/v1"
    keyed        = True
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON, SCHEMA, IMAGES, DOCUMENTS, METADATA}
    tunes        : ClassVar[frozenset[str]] = frozenset(WIRE) - {"top_k"}
    limit        : ClassVar[str] = "max_completion_tokens"

    @override
    def abilities ( self ) -> frozenset[str]:

        if self.model.startswith("text-embedding-"): return VECTORS
        if "transcribe" in self.model or self.model.startswith("whisper"): return HEARING

        return super().abilities()

class DeepSeek(Compatible):

    name         = "deepseek"
    base         = "https://api.deepseek.com/v1"
    keyed        = True
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON}
    tunes        : ClassVar[frozenset[str]] = frozenset({"temperature", "top_p", "stop", "presence", "frequency"})
    efforts      : ClassVar[frozenset[str]] = frozenset()

class Local(Compatible):

    name         = "local"
    capabilities : ClassVar[frozenset[str]] = CORE | {JSON, IMAGES}
