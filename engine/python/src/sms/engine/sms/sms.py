from collections.abc import Sequence
from typing import Any, ClassVar, override

from engine.adapter import Manager, Receipt
from engine.error import Code, Fault
from engine.log import log
from engine.net import Remote, Transport
from engine.string import string
from .text import LogTexter, Text, Texter, phone

TWILIO   = "https://api.twilio.com"
GRAPH    = "https://graph.facebook.com"
VERSION  = "v26.0"
TELEGRAM = "https://api.telegram.org"

class Twilio(Remote, Texter):

    name         = "twilio"
    capabilities : ClassVar[frozenset[str]] = frozenset({"text", "media", "sender"})

    def __init__ (
        self, account: str, token: str, sender: str = "", service: str = "", base: str = "", wait: float = 15.0,
        transport: Transport | None = None,
    ) -> None:

        Remote.__init__(self, base or TWILIO, wait, 2, transport)

        self.missing(("account", account), ("token", token))

        self._account = account
        self._token   = token
        self._sender  = sender
        self._service = service

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Basic {string.to_base64(f'{self._account}:{self._token}')}" }

    @override
    async def deliver ( self, text: Text, number: str, sender: str ) -> dict[str, Any]:

        origin = text.sender or self._sender or sender
        data: dict[str, object] = { "To": phone(number), "Body": text.body or "" }

        if self._service and not text.sender: data["MessagingServiceSid"] = self._service
        else: data["From"] = origin

        if text.links: data["MediaUrl"] = list(text.links)

        found = await self.call("POST", f"/2010-04-01/Accounts/{self._account}/Messages.json", "send", data=data)

        return { "id": found.get("sid", ""), "status": found.get("status", "queued"), **found }

class WhatsApp(Remote, Texter):

    name         = "whatsapp"
    capabilities : ClassVar[frozenset[str]] = frozenset({"text", "template", "media", "sender"})

    def __init__ (
        self, token: str, number: str, version: str = VERSION, base: str = "", wait: float = 15.0,
        transport: Transport | None = None,
    ) -> None:

        Remote.__init__(self, base or GRAPH, wait, 2, transport)

        self.missing(("token", token), ("number", number))

        self._token   = token
        self._number  = number
        self._version = version

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._token}" }

    def body ( self, text: Text, number: str ) -> dict[str, Any]:

        base = { "messaging_product": "whatsapp", "recipient_type": "individual", "to": phone(number).lstrip("+") }

        if text.template_name:

            values     = [{ "type": "text", "text": value } for value in text.template_params]
            components = [{ "type": "body", "parameters": values }] if values else []
            language   = { "policy": "deterministic", "code": text.template_language }
            template   = { "name": text.template_name, "language": language }

            return { **base, "type": "template", "template": { **template, "components": components } }

        if text.links:
            return { **base, "type": "image", "image": { "link": text.links[0], "caption": text.body or "" } }

        return { **base, "type": "text", "text": { "body": text.body or "", "preview_url": False } }

    @override
    async def deliver ( self, text: Text, number: str, sender: str ) -> dict[str, Any]:

        origin = text.sender or self._number
        found  = await self.call("POST", f"/{self._version}/{origin}/messages", "send", json=self.body(text, number))
        sent   = (found.get("messages") or [{}])[0]

        return { "id": sent.get("id", ""), "status": sent.get("message_status", "accepted"), **found }

class Telegram(Remote, Texter):

    name         = "telegram"
    capabilities : ClassVar[frozenset[str]] = frozenset({"text", "media", "silent"})

    def __init__ ( self, token: str, base: str = "", wait: float = 15.0, transport: Transport | None = None ) -> None:

        Remote.__init__(self, base or TELEGRAM, wait, 2, transport)

        self.missing(("token", token))

        self._token = token

    @override
    async def deliver ( self, text: Text, number: str, sender: str ) -> dict[str, Any]:

        chat = number.strip()

        if text.links:
            body: dict[str, Any] = { "chat_id": chat, "photo": text.links[0], "caption": text.body or "" }
            verb = "sendPhoto"
        else:
            body = { "chat_id": chat, "text": text.body or "", "link_preview_options": { "is_disabled": True } }
            verb = "sendMessage"

        if text.silent: body["disable_notification"] = True

        found  = await self.call("POST", f"/bot{self._token}/{verb}", "send", json=body)
        result = found.get("result") or {}

        return { "id": str(result.get("message_id", "")), "status": "sent" if found.get("ok") else "failed", **found }

class Sms(Manager[Texter]):

    def __init__ ( self ) -> None:

        super().__init__("sms")

        self._sender = ""
        self._sent   = 0

    def setup ( self, sender: str = "", texter: Texter | None = None ) -> None:

        self._sender = sender

        if texter is not None: self.register(texter, default=True)

    def sender ( self ) -> str:

        return self._sender

    def draft ( self, body: str = "" ) -> Text:

        return Text.compose(body).bound(self)

    def to ( self, *recipients: str ) -> Text:

        return self.draft().to(*recipients)

    def texter ( self, text: Text, using: str | None = None ) -> Texter:

        chosen = self.use(using or text.provider)

        chosen.check(text)

        return chosen

    def prepare ( self, item: Any, using: str | None = None ) -> dict[str, Any]:

        text = self.text(item)

        return self.texter(text, using).prepare(text, self._sender)

    async def send ( self, item: Any, using: str | None = None ) -> Receipt:

        text    = self.text(item)
        texter  = self.texter(text, using)
        receipt = await texter.send(text, self._sender)

        self._sent += 1

        log.info("sms.sent", to=list(text.recipients), texter=texter.name, id=receipt.id, status=receipt.status)

        return receipt

    async def send_many ( self, texts: Sequence[Text], using: str | None = None ) -> list[Receipt]:

        return [await self.send(text, using) for text in texts]

    def text ( self, item: Any ) -> Text:

        if not isinstance(item, Text): raise Fault(Code.INTERNAL, reason="sms.text")

        return item

    def outbox ( self ) -> LogTexter:

        found = self.use()

        if not isinstance(found, LogTexter): raise Fault(Code.INTERNAL, reason="sms.outbox")

        return found

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "sender": self._sender, "sent": self._sent }
