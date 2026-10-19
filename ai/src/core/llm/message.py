from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, Self

from core.fs import Extraction, ExtractPolicy
from core.thread import thread
from core.error import Code, Fault
from core.json import Shape, json
from core.string import string

type Role = Literal["system", "user", "assistant"]

IMAGES = ("image/png", "image/jpeg", "image/gif", "image/webp")
TEXTS  = ("text/", "application/json", "application/xml", "application/x-yaml", "application/toml")

@dataclass(frozen=True, slots=True)
class Attachment:

    name : str
    data : bytes
    mime : str = "application/octet-stream"

    @classmethod
    async def from_path ( cls, path: Path | str, mime: str | None = None ) -> Self:

        name, data, detected = await thread.offload(Extraction().read, path, ExtractPolicy())
        if mime is not None and mime != detected: raise Fault(Code.VALIDATION, reason="llm.attachment.mime")
        return cls(name, data, detected)

    @classmethod
    def text ( cls, name: str, content: str, mime: str = "text/plain" ) -> Self:

        return cls(name, content.encode(), mime)

    def is_image ( self ) -> bool:

        return self.mime in IMAGES

    def is_text ( self ) -> bool:

        return self.mime.startswith(TEXTS)

    def is_pdf ( self ) -> bool:

        return self.mime == "application/pdf"

    def base64 ( self ) -> str:

        return string.to_base64(self.data)

    def data_url ( self ) -> str:

        return f"data:{self.mime};base64,{self.base64()}"

    def plain ( self ) -> str:

        return self.data.decode(errors="replace")

    def size ( self ) -> int:

        return len(self.data)

@dataclass(frozen=True, slots=True)
class Message:

    role        : Role
    content     : str
    attachments : tuple[Attachment, ...] = ()
    name        : str | None = None

    @classmethod
    def system ( cls, content: str ) -> Self:

        return cls("system", content)

    @classmethod
    def user ( cls, content: str, *attachments: Attachment ) -> Self:

        return cls("user", content, tuple(attachments))

    @classmethod
    def assistant ( cls, content: str ) -> Self:

        return cls("assistant", content)

    def with_attachments ( self, *attachments: Attachment ) -> Self:

        return replace(self, attachments=(*self.attachments, *attachments))

    def dump ( self ) -> dict[str, Any]:

        return {
            "role": self.role, "content": self.content, "name": self.name,
            "attachments": [
                {"name": item.name, "mime": item.mime, "data": item.base64()} for item in self.attachments
            ],
        }

    @classmethod
    def load ( cls, data: Mapping[str, Any] ) -> Self:

        return cls(
            data["role"], str(data.get("content", "")),
            tuple(Attachment(item["name"], string.from_base64(item["data"]), item["mime"])
                  for item in data.get("attachments", [])), name=data.get("name"),
        )

@dataclass(frozen=True, slots=True)
class Usage:

    input  : int = 0
    output : int = 0

    def total ( self ) -> int:

        return self.input + self.output

    def plus ( self, other: Usage ) -> Usage:

        return Usage(self.input + other.input, self.output + other.output)

    def dump ( self ) -> dict[str, int]:

        return { "input": self.input, "output": self.output, "total": self.total() }

@dataclass(frozen=True, slots=True)
class Reply:

    text     : str
    model    : str
    provider : str
    usage    : Usage = field(default_factory=Usage)
    finish   : str | None = None
    ms       : float = 0.0
    raw      : Any = field(default=None, compare=False, repr=False)

    def message ( self ) -> Message:

        return Message.assistant(self.text)

    def json ( self ) -> Any:

        text  = self.text.strip()
        inner = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        return json.parse(inner)

    def dump ( self ) -> dict[str, Any]:

        return {
            "text": self.text, "model": self.model, "provider": self.provider, "usage": self.usage.dump(),
            "finish": self.finish, "ms": self.ms,
        }

@dataclass(frozen=True, slots=True)
class Chunk:

    text  : str
    done  : bool = False
    usage : Usage | None = None
    raw   : Any = field(default=None, compare=False, repr=False)

@dataclass(frozen=True, slots=True)
class Options:

    model       : str | None = None
    system      : str | None = None
    temperature : float | None = None
    max_tokens  : int | None = None
    top_p       : float | None = None
    stop        : tuple[str, ...] = ()
    json        : bool = False
    metadata    : Mapping[str, Any] = field(default_factory=dict)
    schema      : Shape | None = None
    native_schema: bool = True

    def merged ( self, **changes: Any ) -> Options:

        return replace(self, **{ key: value for key, value in changes.items() if value is not None })

    def generation ( self ) -> dict[str, Any]:

        found: dict[str, Any] = {}

        if self.temperature is not None: found["temperature"] = self.temperature
        if self.max_tokens is not None: found["max_tokens"] = self.max_tokens
        if self.top_p is not None: found["top_p"] = self.top_p
        if self.stop: found["stop"] = list(self.stop)

        return found

def conversation ( messages: Sequence[Message], options: Options ) -> list[Message]:

    history = [message for message in messages if message.role != "system"]
    system  = options.system or next((message.content for message in messages if message.role == "system"), None)

    return [Message.system(system), *history] if system else history
