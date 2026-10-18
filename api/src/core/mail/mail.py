from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formataddr

from core.error import Code, Fault
from core.log import log
from .message import Message
from .transport import Transport

class Mail:

    def __init__ ( self ) -> None:

        self._transport: Transport | None = None
        self._sender = ""
        self._name   = ""
        self._sent   = 0

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

    def draft ( self, subject: str = "" ) -> Message:
        return Message.compose(subject)

    async def send ( self, message: Message ) -> None:

        transport = self.transport()

        if not message.to: raise Fault(Code.BAD_REQUEST, reason="mail.to")
        if not (message.html or message.text): raise Fault(Code.BAD_REQUEST, reason="mail.body")

        sender = message.sender or self.sender()
        raw    = self.compose(message, sender)

        await transport.send(message, raw, sender, message.recipients())

        self._sent += 1

        log.info("mail.sent", to=list(message.to), subject=message.subject, transport=transport.name)

    async def send_many ( self, messages: Sequence[Message] ) -> int:

        for message in messages: await self.send(message)

        return len(messages)

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

    def raw ( self, message: Message ) -> EmailMessage:
        return self.compose(message, message.sender or self.sender())

    def describe ( self ) -> dict[str, object]:

        return {
            "ready": self.ready(), "transport": self._transport.name if self._transport else None,
            "sender": self._sender, "sent": self._sent,
        }
