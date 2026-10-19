from collections.abc import Sequence
from core.error import Code, Fault
from .capability import Capabilities
from .message import Attachment, Message, Options

MAX_TEMPERATURE = 2

def attachment ( capabilities: Capabilities, item: Attachment ) -> None:

    if item.is_text(): return
    if item.is_image(): capabilities.require("image")
    elif item.is_pdf(): capabilities.require("pdf")
    elif item.mime.startswith("audio/"): capabilities.require("audio")
    elif item.mime.startswith("video/"): capabilities.require("video")
    else: raise Fault(Code.VALIDATION, reason="llm.unsupported.attachment")

def validate ( capabilities: Capabilities, messages: Sequence[Message], options: Options ) -> None:

    capabilities.require("generate")
    if options.json: capabilities.require("json")
    if options.schema is not None and options.native_schema: capabilities.require("schema")
    if options.metadata: raise Fault(Code.VALIDATION, reason="llm.unsupported.metadata")
    if options.max_tokens is not None and options.max_tokens < 1:
        raise Fault(Code.VALIDATION, reason="llm.options.tokens")
    if options.temperature is not None and not 0 <= options.temperature <= MAX_TEMPERATURE:
        raise Fault(Code.VALIDATION, reason="llm.options.temperature")
    if options.top_p is not None and not 0 < options.top_p <= 1:
        raise Fault(Code.VALIDATION, reason="llm.options.top_p")
    for message in messages:
        for item in message.attachments: attachment(capabilities, item)

def dedicated ( options: Options, model: str, attached: bool ) -> None:

    if options.model not in (None, model): raise Fault(Code.VALIDATION, reason="llm.dedicated.model")
    if options.system or options.generation() or options.json or options.schema or options.metadata or attached:
        raise Fault(Code.VALIDATION, reason="llm.dedicated.options")
