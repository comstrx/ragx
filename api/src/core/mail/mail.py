from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr
from typing import Protocol

from core.exceptions import Code, Fault
from core.log import log
import aiosmtplib, ssl

@dataclass(frozen=True, slots=True)
class Attachment:

    name    : str
    content : bytes
    type    : str = "application/octet-stream"

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

    def recipients ( self ) -> tuple[str, ...]:
        return (*self.to, *self.cc, *self.bcc)

class Transport(Protocol):

    async def send ( self, message: Message, raw: EmailMessage, sender: str, recipients: Sequence[str] ) -> None: ...

class SmtpTransport:

    def __init__ (
        self, host: str, port: int = 587, username: str | None = None, password: str | None = None,
        tls: bool = True, ssl: bool = False, timeout: float = 10.0, verify: bool = True,
    ) -> None:

        self._host     = host
        self._port     = port
        self._username = username
        self._password = password
        self._tls      = tls
        self._ssl      = ssl
        self._timeout  = timeout
        self._verify   = verify

    async def send ( self, _message: Message, raw: EmailMessage, sender: str, recipients: Sequence[str] ) -> None:

        try:

            await aiosmtplib.send(
                raw, sender=sender, recipients=list(recipients), hostname=self._host, port=self._port,
                username=self._username, password=self._password, start_tls=self._tls and not self._ssl,
                use_tls=self._ssl, timeout=self._timeout, tls_context=self.context(),
            )

        except (aiosmtplib.SMTPException, OSError) as error: raise Fault(Code.UNAVAILABLE, reason="mail") from error

    def context ( self ) -> ssl.SSLContext | None:

        if self._verify: return None

        context = ssl.create_default_context()

        context.check_hostname = False
        context.verify_mode    = ssl.CERT_NONE

        return context

class LogTransport:

    async def send ( self, message: Message, raw: EmailMessage, _sender: str, recipients: Sequence[str] ) -> None:

        size = len(raw.as_bytes())

        log.info("mail.logged", to=list(recipients), subject=message.subject, bytes=size)

class MemoryTransport:

    def __init__ ( self ) -> None:

        self.outbox: list[Message] = []

    async def send ( self, message: Message, _raw: EmailMessage, _sender: str, _recipients: Sequence[str] ) -> None:
        self.outbox.append(message)

    def last ( self ) -> Message | None:
        return self.outbox[-1] if self.outbox else None

    def clear ( self ) -> None:
        self.outbox.clear()

class Mail:

    def __init__ ( self ) -> None:

        self._transport: Transport | None = None
        self._sender = ""
        self._name   = ""

    def setup ( self, transport: Transport, sender: str, name: str = "" ) -> None:

        if not sender: raise Fault(Code.INTERNAL, reason="mail.sender")

        self._transport = transport
        self._sender    = sender
        self._name      = name

    def ready ( self ) -> bool:
        return self._transport is not None

    def transport ( self ) -> Transport:

        if self._transport is None: raise Fault(Code.INTERNAL, reason="mail")

        return self._transport

    def sender ( self ) -> str:
        return formataddr((self._name, self._sender)) if self._name else self._sender

    async def send ( self, message: Message ) -> None:

        if self._transport is None: raise Fault(Code.INTERNAL, reason="mail")
        if not message.to: raise Fault(Code.BAD_REQUEST, reason="mail.to")
        if not (message.html or message.text): raise Fault(Code.BAD_REQUEST, reason="mail.body")

        sender = message.sender or self.sender()
        raw    = self.compose(message, sender)

        await self._transport.send(message, raw, sender, message.recipients())
        log.info("mail.sent", to=list(message.to), subject=message.subject)

    def compose ( self, message: Message, sender: str ) -> EmailMessage:

        raw = EmailMessage()

        raw["From"]    = sender
        raw["To"]      = ", ".join(message.to)
        raw["Subject"] = message.subject

        if message.cc: raw["Cc"] = ", ".join(message.cc)
        if message.reply_to: raw["Reply-To"] = message.reply_to

        for name, value in message.headers.items(): raw[name] = value

        raw.set_content(message.text or "")

        if message.html: raw.add_alternative(message.html, subtype="html")

        for attachment in message.attachments:

            main, _, sub = attachment.type.partition("/")

            raw.add_attachment(
                attachment.content, maintype=main or "application", subtype=sub or "octet-stream",
                filename=attachment.name,
            )

        return raw
