from collections.abc import AsyncGenerator, Sequence
from typing import Any, ClassVar, override

from core.date import date
from core.json import Schema
from core.net import Transport
from .message import Attachment, Chunk, Message, Options, Reply, Usage
from .provider import CORE, DOCUMENTS, IMAGES, METADATA, SCHEMA, Provider, text_of
import contextlib

BASE    = "https://api.anthropic.com"
MODEL   = "claude-sonnet-5-5"
VERSION = "2023-06-01"
TOKENS  = 4096
LIMITED = frozenset({"minimum", "maximum", "minLength", "maxLength", "maxItems"})

class Claude(Provider):

    name         = "claude"
    model        = MODEL
    capabilities : ClassVar[frozenset[str]] = CORE | {SCHEMA, IMAGES, DOCUMENTS, METADATA}

    def __init__ (
        self, key: str, model: str | None = None, base: str | None = None, wait: float = 60.0, retries: int = 1,
        transport: Transport | None = None,
    ) -> None:

        self.missing(("key", key))

        super().__init__(base or BASE, key, model, wait, retries, transport)

    @override
    def headers ( self ) -> dict[str, str]:

        return { "x-api-key": self._key, "anthropic-version": VERSION }

    def part ( self, attachment: Attachment ) -> dict[str, Any]:

        source = { "type": "base64", "media_type": attachment.mime, "data": attachment.base64() }

        if attachment.is_image(): return { "type": "image", "source": source }
        if attachment.is_pdf(): return { "type": "document", "source": source, "title": attachment.name }

        text = { "type": "text", "media_type": "text/plain", "data": attachment.plain() }

        return { "type": "document", "source": text, "title": attachment.name }

    def content ( self, message: Message ) -> Any:

        if not message.attachments: return message.content

        parts = [self.part(item) for item in message.attachments]

        return [*parts, { "type": "text", "text": message.content }] if message.content else parts

    def body ( self, messages: Sequence[Message], options: Options, stream: bool = False ) -> dict[str, Any]:

        system  = options.system or next((message.content for message in messages if message.role == "system"), None)
        turns   = [message for message in messages if message.role != "system"]
        payload: dict[str, Any] = {
            "model": self.pick(options), "max_tokens": options.max_tokens or TOKENS,
            "messages": [{ "role": message.role, "content": self.content(message) } for message in turns],
        }

        if system: payload["system"] = system
        if options.temperature is not None: payload["temperature"] = options.temperature
        if options.top_p is not None: payload["top_p"] = options.top_p
        if options.stop: payload["stop_sequences"] = list(options.stop)
        if options.metadata: payload["metadata"] = dict(options.metadata)
        if options.schema is not None and options.native:
            payload["output_config"] = { "format": { "type": "json_schema", "schema": self.shaped(options.schema) } }
        if stream: payload["stream"] = True

        return payload

    @override
    def shaped ( self, schema: Schema ) -> dict[str, Any]:

        return schema.projected(LIMITED, items=1)

    def usage_of ( self, data: Any ) -> Usage:

        usage = data.get("usage") if isinstance(data, dict) else None

        if not isinstance(usage, dict): return Usage()

        return Usage(int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0))

    @override
    async def answer ( self, messages: Sequence[Message], options: Options ) -> Reply:

        started = date.tick()
        data    = await self.post("/v1/messages", self.body(messages, options))

        return Reply(
            text_of(data.get("content")), str(data.get("model") or self.pick(options)), self.name,
            self.usage_of(data), data.get("stop_reason"), date.elapsed(started), data,
        )

    @override
    async def chunks ( self, messages: Sequence[Message], options: Options ) -> AsyncGenerator[Chunk]:

        spent = Usage()

        async with contextlib.aclosing(self.flow("/v1/messages", self.body(messages, options, stream=True))) as events:

            async for event in events:

                data = event.json()

                if not isinstance(data, dict): continue

                kind = str(data.get("type", ""))

                if kind == "message_start": spent = self.usage_of(data.get("message"))
                if kind == "content_block_delta":

                    delta = data.get("delta") or {}

                    if delta.get("type") == "text_delta": yield Chunk(str(delta.get("text", "")), raw=data)

                if kind == "message_delta": spent = spent.plus(self.usage_of(data))
                if kind == "message_stop":

                    yield Chunk("", done=True, usage=spent, raw=data)

                    return

    @override
    async def models ( self ) -> list[str]:

        data  = await self.listing("/v1/models")
        found = data.get("data") if isinstance(data, dict) else []

        if not isinstance(found, list): return []

        return sorted(str(item.get("id")) for item in found if isinstance(item, dict))
