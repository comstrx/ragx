from collections.abc import Sequence
from dataclasses import dataclass, replace

from core.error import Code, Fault
from core.string import string
from .message import Attachment, Message, Options
import math

TEMPERATURE = 2.0
ATTACHED    = 16 * 1024 * 1024
STOPS       = 4
TURN        = 2
SMALLEST    = 256

@dataclass(frozen=True, slots=True)
class Harness:

    instructions  : tuple[str, ...] = ()
    redact        : bool = False
    reject        : bool = False
    input_chars   : int = 48_000
    output_tokens : int = 2048
    timeout       : float = 120.0
    region        : str = "EG"

    def __post_init__ ( self ) -> None:

        if self.input_chars < 1 or self.output_tokens < 1 or self.timeout <= 0:
            raise Fault(Code.VALIDATION, reason="llm.harness.limits")

    def merge ( self, other: Harness ) -> Harness:

        return Harness(
            tuple(dict.fromkeys((*self.instructions, *other.instructions))), self.redact or other.redact,
            self.reject or other.reject, min(self.input_chars, other.input_chars),
            min(self.output_tokens, other.output_tokens), min(self.timeout, other.timeout), other.region,
        )

    def prepare ( self, messages: Sequence[Message], options: Options ) -> tuple[tuple[Message, ...], Options]:

        self.check(options)

        system   = "\n\n".join(filter(None, (*self.instructions, options.system))) or None
        attached = [attachment for message in messages for attachment in message.attachments]
        written  = sum(len(message.content) for message in messages) + len(system or "")
        written += sum(len(attachment.plain()) for attachment in attached if attachment.is_text())

        if sum(attachment.size() for attachment in attached) > ATTACHED:
            raise Fault(Code.VALIDATION, reason="llm.harness.attachments")
        if written > self.input_chars: raise Fault(Code.VALIDATION, reason="llm.harness.input")

        cleaned = tuple(self.message(message) for message in messages)
        budget  = min(options.max_tokens or self.output_tokens, self.output_tokens)

        return cleaned, replace(options, system=system, max_tokens=budget)

    def guarded ( self ) -> bool:

        return self.redact or self.reject

    def message ( self, message: Message ) -> Message:

        if message.role == "system" or not self.guarded(): return message

        content = string.guard(message.content, self.reject and message.role == "user", self.redact, self.region)

        return replace(message, content=content, attachments=tuple(map(self.attachment, message.attachments)))

    def attachment ( self, attachment: Attachment ) -> Attachment:

        if not self.guarded(): return attachment
        if not attachment.is_text(): raise Fault(Code.VALIDATION, reason="llm.harness.binary")

        cleaned = string.guard(attachment.plain(), self.reject, self.redact, self.region)

        return Attachment.text(attachment.name, cleaned, attachment.mime)

    def texts ( self, values: Sequence[str] ) -> tuple[str, ...]:

        if sum(map(len, values)) > self.input_chars: raise Fault(Code.VALIDATION, reason="llm.harness.input")

        return tuple(string.guard(value, self.reject, self.redact, self.region) for value in values)

    def check ( self, options: Options ) -> None:

        if options.max_tokens is not None and options.max_tokens < 1:
            raise Fault(Code.VALIDATION, reason="llm.options.tokens")
        if options.temperature is not None and not 0 <= options.temperature <= TEMPERATURE:
            raise Fault(Code.VALIDATION, reason="llm.options.temperature")
        if options.top_p is not None and not 0 < options.top_p <= 1:
            raise Fault(Code.VALIDATION, reason="llm.options.top_p")
        if len(options.stop) > STOPS: raise Fault(Code.VALIDATION, reason="llm.options.stop")

    def dedicated ( self, options: Options, model: str, bound: bool ) -> None:

        if options.model not in (None, model): raise Fault(Code.VALIDATION, reason="llm.dedicated.model")

        chosen = options.system or options.generation() or options.json or options.schema or options.metadata

        if chosen or bound: raise Fault(Code.VALIDATION, reason="llm.dedicated.options")

@dataclass(frozen=True, slots=True)
class Memory:

    window : int = 8192
    ratio  : float = 0.7
    keep   : int = 4
    chars  : float = 3.0

    def __post_init__ ( self ) -> None:

        sane = self.window >= SMALLEST and 0 < self.ratio <= 1 and self.chars > 0

        if not sane or self.keep < TURN or self.keep % TURN: raise Fault(Code.VALIDATION, reason="llm.memory")

    def tokens ( self, *texts: str | None ) -> int:

        return math.ceil(sum(len(text or "") for text in texts) / self.chars)

    def due ( self, used: int ) -> bool:

        return used > self.ratio * self.window
