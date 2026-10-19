from collections.abc import Sequence
from email.message import EmailMessage
from typing import Protocol

from core.error import Code, Fault
from core.log import log
from .message import Message
import aiosmtplib, ssl

class Transport(Protocol):

    @property
    def name ( self ) -> str: ...

    async def send ( self, message: Message, raw: EmailMessage, sender: str, recipients: Sequence[str] ) -> None: ...

class SmtpTransport:

    name = "smtp"

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

    async def ping ( self ) -> bool:

        try:

            client = aiosmtplib.SMTP(hostname=self._host, port=self._port, timeout=self._timeout, use_tls=self._ssl)

            await client.connect()
            await client.quit()

        except (aiosmtplib.SMTPException, OSError): return False

        return True

class LogTransport:

    name = "log"

    async def send ( self, message: Message, raw: EmailMessage, _sender: str, recipients: Sequence[str] ) -> None:

        log.info("mail.logged", to=list(recipients), subject=message.subject, bytes=len(raw.as_bytes()))

class MemoryTransport:

    name = "memory"

    def __init__ ( self ) -> None:

        self.outbox: list[Message] = []

    async def send ( self, message: Message, _raw: EmailMessage, _sender: str, _recipients: Sequence[str] ) -> None:

        self.outbox.append(message)

    def last ( self ) -> Message | None:

        return self.outbox[-1] if self.outbox else None

    def sent_to ( self, address: str ) -> list[Message]:

        return [message for message in self.outbox if address in message.recipients()]

    def count ( self ) -> int:

        return len(self.outbox)

    def clear ( self ) -> int:

        count = len(self.outbox)

        self.outbox.clear()

        return count
