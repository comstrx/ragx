from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from email.utils import formataddr
from typing import Any, ClassVar, Self, override

from core.adapter import Adapter, Manager, Outgoing, Piece, Receipt
from core.error import Code, Fault
from core.log import log
from core.net import Remote, Transport
from core.rand import rand
from core.string import string

Attachment = Piece
REGIONS    = { "us": "https://api.mailgun.net", "eu": "https://api.eu.mailgun.net" }
FEATURES   = frozenset({"text", "html", "attachments", "cc", "bcc", "headers", "tags", "metadata", "reply"})

@dataclass(frozen=True, slots=True, kw_only=True)
class Message(Outgoing):

    subject : str = ""
    markup  : str | None = None
    copies  : tuple[str, ...] = ()
    hidden  : tuple[str, ...] = ()
    reply   : str | None = None
    headers : Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def compose ( cls, subject: str = "" ) -> Self:

        return cls(subject=subject)

    def about ( self, subject: str ) -> Self:

        return replace(self, subject=subject)

    def html ( self, markup: str ) -> Self:

        return replace(self, markup=markup)

    def cc ( self, *addresses: str ) -> Self:

        return replace(self, copies=(*self.copies, *addresses))

    def bcc ( self, *addresses: str ) -> Self:

        return replace(self, hidden=(*self.hidden, *addresses))

    def reply_to ( self, address: str ) -> Self:

        return replace(self, reply=address)

    def header ( self, name: str, value: str ) -> Self:

        return replace(self, headers={ **self.headers, name: value })

    def everyone ( self ) -> tuple[str, ...]:

        return (*self.recipients, *self.copies, *self.hidden)

    def features ( self ) -> list[str]:

        found = [
            ("html", self.markup), ("attachments", self.attachments), ("cc", self.copies), ("bcc", self.hidden),
            ("headers", self.headers), ("tags", self.tags), ("metadata", self.metadata), ("reply", self.reply),
        ]

        return [name for name, value in found if value]

    @override
    def size ( self ) -> int:

        return len(self.markup or "") + Outgoing.size(self)

    def dump ( self ) -> dict[str, Any]:

        return {
            **self.shared(), "subject": self.subject, "html": self.markup, "cc": list(self.copies),
            "bcc": list(self.hidden), "reply_to": self.reply, "headers": dict(self.headers),
        }

class Mailer(Adapter, ABC):

    family       : ClassVar[str] = "mail"
    capabilities : ClassVar[frozenset[str]] = FEATURES

    def check ( self, message: Message ) -> None:

        if not message.recipients: raise Fault(Code.BAD_REQUEST, reason="mail.to")
        if not (message.markup or message.body): raise Fault(Code.BAD_REQUEST, reason="mail.body")

        for feature in message.features(): self.require(feature)

    def prepare ( self, message: Message, sender: str ) -> dict[str, Any]:

        return { "from": sender, **message.dump() }

    @abstractmethod
    async def send ( self, message: Message, sender: str ) -> Receipt: ...

class LogMailer(Mailer):

    name = "log"

    def __init__ ( self, keep: int = 500 ) -> None:

        self.outbox: list[Message] = []
        self._keep  = keep

    @override
    async def send ( self, message: Message, sender: str ) -> Receipt:

        self.outbox.append(message)

        del self.outbox[:-self._keep]

        log.info("mail.logged", to=list(message.recipients), subject=message.subject, sender=sender)

        return Receipt(provider=self.name, id=f"log-{rand.hex(6)}", status="logged", to=message.everyone())

    def last ( self ) -> Message | None:

        return self.outbox[-1] if self.outbox else None

    def sent_to ( self, address: str ) -> list[Message]:

        return [message for message in self.outbox if address in message.everyone()]

    def count ( self ) -> int:

        return len(self.outbox)

    def clear ( self ) -> int:

        count = len(self.outbox)

        self.outbox.clear()

        return count

class Mailgun(Remote, Mailer):

    name         = "mailgun"
    capabilities : ClassVar[frozenset[str]] = FEATURES | frozenset({"schedule"})

    def __init__ (
        self, key: str, domain: str, region: str = "us", base: str = "", wait: float = 20.0,
        transport: Transport | None = None,
    ) -> None:

        Remote.__init__(self, base or REGIONS.get(region.lower(), REGIONS["us"]), wait, 2, transport)

        self.missing(("key", key), ("domain", domain))

        self._key    = key
        self._domain = domain

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Basic {string.to_base64(f'api:{self._key}')}" }

    @override
    def prepare ( self, message: Message, sender: str ) -> dict[str, Any]:

        fields: dict[str, Any] = {
            "from": sender, "to": list(message.recipients), "subject": message.subject,
            "text": message.body, "html": message.markup, "cc": list(message.copies) or None,
            "bcc": list(message.hidden) or None, "o:tag": list(message.tags) or None,
        }

        if message.reply: fields["h:Reply-To"] = message.reply

        for name, value in message.headers.items(): fields[f"h:{name}"] = value
        for name, value in message.metadata.items(): fields[f"v:{name}"] = value

        return { key: value for key, value in fields.items() if value not in (None, "") }

    @override
    async def send ( self, message: Message, sender: str ) -> Receipt:

        data  = self.prepare(message, sender)
        files = {
            f"attachment[{index}]": (item.name, item.content, item.type)
            for index, item in enumerate(message.attachments)
        }
        found = await self.call("POST", f"/v3/{self._domain}/messages", "send", data=data, files=files or None)

        return Receipt(
            provider=self.name, id=str(found.get("id", "")).strip("<>"), status="queued", to=message.everyone(),
            raw=dict(found),
        )

class Mail(Manager[Mailer]):

    def __init__ ( self ) -> None:

        super().__init__("mail")

        self._sender = ""
        self._name   = ""
        self._sent   = 0

    def setup ( self, sender: str, name: str = "", mailer: Mailer | None = None ) -> None:

        if not sender: raise Fault(Code.INTERNAL, reason="mail.sender")

        self._sender = sender
        self._name   = name

        if mailer is not None: self.register(mailer, default=True)

    def sender ( self ) -> str:

        return formataddr((self._name, self._sender)) if self._name else self._sender

    def draft ( self, subject: str = "" ) -> Message:

        return Message.compose(subject).bound(self)

    def to ( self, *recipients: str ) -> Message:

        return self.draft().to(*recipients)

    def mailer ( self, message: Message, using: str | None = None ) -> Mailer:

        chosen = self.use(using or message.provider)

        chosen.check(message)

        return chosen

    def prepare ( self, item: Any, using: str | None = None ) -> dict[str, Any]:

        message = self.message(item)

        return self.mailer(message, using).prepare(message, message.sender or self.sender())

    async def send ( self, item: Any, using: str | None = None ) -> Receipt:

        message = self.message(item)
        mailer  = self.mailer(message, using)
        receipt = await mailer.send(message, message.sender or self.sender())

        self._sent += 1

        log.info("mail.sent", to=list(message.recipients), subject=message.subject, mailer=mailer.name, id=receipt.id)

        return receipt

    async def send_many ( self, messages: Sequence[Message], using: str | None = None ) -> list[Receipt]:

        return [await self.send(message, using) for message in messages]

    def message ( self, item: Any ) -> Message:

        if not isinstance(item, Message): raise Fault(Code.INTERNAL, reason="mail.message")

        return item

    def outbox ( self ) -> LogMailer:

        found = self.use()

        if not isinstance(found, LogMailer): raise Fault(Code.INTERNAL, reason="mail.outbox")

        return found

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "sender": self._sender, "sent": self._sent }
