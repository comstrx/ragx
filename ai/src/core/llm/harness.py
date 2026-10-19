from dataclasses import dataclass, replace
from core.error import Code, Fault
from core.string import safety
from .message import Attachment, Message, Options

@dataclass(frozen=True, slots=True)
class Harness:

    instructions     : tuple[str, ...] = ()
    redact           : bool = False
    reject_injection : bool = False
    max_input_chars  : int = 24_000
    max_output_tokens: int = 512
    timeout          : float = 120.0

    def __post_init__ ( self ) -> None:

        if self.max_input_chars < 1 or self.max_output_tokens < 1 or self.timeout <= 0:
            raise Fault(Code.VALIDATION, reason="harness.limits")

    def merge ( self, other: Harness ) -> Harness:

        return Harness(
            (*self.instructions, *other.instructions), self.redact or other.redact,
            self.reject_injection or other.reject_injection, min(self.max_input_chars, other.max_input_chars),
            min(self.max_output_tokens, other.max_output_tokens), min(self.timeout, other.timeout),
        )

    def prepare ( self, messages: tuple[Message, ...], options: Options ) -> tuple[tuple[Message, ...], Options]:

        total = sum(len(item.content) for item in messages) + len(options.system or "")
        total += sum(map(len, self.instructions))
        files = [file for item in messages for file in item.attachments]
        total += sum(len(file.plain()) for file in files if file.is_text())
        if sum(file.size() for file in files) > 16 * 1024 * 1024:
            raise Fault(Code.VALIDATION, reason="harness.attachments.limit")
        if total > self.max_input_chars:
            raise Fault(Code.VALIDATION, reason="harness.input.limit")

        cleaned = tuple(
            replace(item, content=safety.guard(item.content, self.reject_injection, self.redact),
                    attachments=tuple(self.attachment(file) for file in item.attachments))
            if item.role != "system" else item for item in messages
        )
        instructions = "\n\n".join((*self.instructions, options.system or "")).strip()
        budget = min(options.max_tokens or self.max_output_tokens, self.max_output_tokens)

        return cleaned, replace(options, system=instructions or None, max_tokens=budget)

    def attachment ( self, attachment: Attachment ) -> Attachment:

        if attachment.size() > 16 * 1024 * 1024:
            raise Fault(Code.VALIDATION, reason="harness.attachment.limit")
        if not self.redact and not self.reject_injection: return attachment
        if not attachment.is_text():
            raise Fault(Code.VALIDATION, reason="harness.attachment.requires_extraction")
        return Attachment.text(
            attachment.name, safety.guard(attachment.plain(), self.reject_injection, self.redact), attachment.mime,
        )

    def texts ( self, values: tuple[str, ...] ) -> tuple[str, ...]:

        if sum(map(len, values)) > self.max_input_chars:
            raise Fault(Code.VALIDATION, reason="harness.input.limit")

        return tuple(safety.guard(value, self.reject_injection, self.redact) for value in values)
