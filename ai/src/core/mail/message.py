from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Self

@dataclass(frozen=True, slots=True)
class Attachment:

    name    : str
    content : bytes
    type    : str = "application/octet-stream"

    def dump ( self ) -> dict[str, object]:

        return { "name": self.name, "type": self.type, "size": len(self.content) }

@dataclass(frozen=True, slots=True)
class Message:

    to          : tuple[str, ...]
    subject     : str
    html        : str | None = None
    text        : str | None = None
    cc          : tuple[str, ...] = ()
    bcc         : tuple[str, ...] = ()
    sender      : str | None = None
    reply_to    : str | None = None
    attachments : tuple[Attachment, ...] = ()
    headers     : Mapping[str, str] = field(default_factory=dict)
    tags        : tuple[str, ...] = ()

    @classmethod
    def compose ( cls, subject: str = "" ) -> Self:

        return cls((), subject)

    def recipients ( self ) -> tuple[str, ...]:

        return (*self.to, *self.cc, *self.bcc)

    def send_to ( self, *addresses: str ) -> Self:

        return replace(self, to=(*self.to, *addresses))

    def copy_to ( self, *addresses: str ) -> Self:

        return replace(self, cc=(*self.cc, *addresses))

    def blind_to ( self, *addresses: str ) -> Self:

        return replace(self, bcc=(*self.bcc, *addresses))

    def about ( self, subject: str ) -> Self:

        return replace(self, subject=subject)

    def with_html ( self, html: str ) -> Self:

        return replace(self, html=html)

    def with_text ( self, text: str ) -> Self:

        return replace(self, text=text)

    def from_ ( self, sender: str ) -> Self:

        return replace(self, sender=sender)

    def reply ( self, address: str ) -> Self:

        return replace(self, reply_to=address)

    def attach ( self, name: str, content: bytes, kind: str = "application/octet-stream" ) -> Self:

        return replace(self, attachments=(*self.attachments, Attachment(name, content, kind)))

    def header ( self, name: str, value: str ) -> Self:

        return replace(self, headers={ **self.headers, name: value })

    def tagged ( self, *tags: str ) -> Self:

        return replace(self, tags=(*self.tags, *tags))

    def size ( self ) -> int:

        return len(self.html or "") + len(self.text or "") + sum(len(item.content) for item in self.attachments)

    def dump ( self ) -> dict[str, object]:

        return {
            "to": list(self.to), "cc": list(self.cc), "bcc": list(self.bcc), "subject": self.subject,
            "sender": self.sender, "reply_to": self.reply_to, "html": self.html, "text": self.text,
            "attachments": [item.dump() for item in self.attachments], "headers": dict(self.headers),
            "tags": list(self.tags),
        }
