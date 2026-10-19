from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import Any, ClassVar, Self, override

from core.adapter import Adapter, Outgoing, Receipt
from core.error import Code, Fault
from core.log import log
from core.rand import rand
from core.string import string

@dataclass(frozen=True, slots=True, kw_only=True)
class Text(Outgoing):

    template_name     : str | None = None
    template_language : str = "en"
    template_params   : tuple[str, ...] = ()
    links             : tuple[str, ...] = ()
    silent            : bool = False

    @classmethod
    def compose ( cls, body: str = "" ) -> Self:

        return cls(body=body or None)

    def template ( self, name: str, language: str = "en", *params: str ) -> Self:

        return replace(self, template_name=name, template_language=language, template_params=params)

    def media ( self, *urls: str ) -> Self:

        return replace(self, links=(*self.links, *urls))

    def quietly ( self ) -> Self:

        return replace(self, silent=True)

    def features ( self ) -> list[str]:

        found = [
            ("template", self.template_name), ("media", self.links), ("sender", self.sender),
            ("attachments", self.attachments), ("tags", self.tags), ("metadata", self.metadata),
            ("silent", self.silent),
        ]

        return [name for name, value in found if value]

    def dump ( self ) -> dict[str, Any]:

        return {
            **self.shared(), "template": self.template_name, "language": self.template_language,
            "params": list(self.template_params), "media": list(self.links), "silent": self.silent,
        }

def phone ( value: str ) -> str:

    cleaned = string.latin_digits(value).strip()
    digits  = "".join(char for char in cleaned if char.isdigit())

    if cleaned.startswith("+"): return f"+{digits}"
    if cleaned.startswith("00"): return f"+{digits[2:]}"

    return digits

class Texter(Adapter, ABC):

    family       : ClassVar[str] = "sms"
    capabilities : ClassVar[frozenset[str]] = frozenset({"text"})

    def check ( self, text: Text ) -> None:

        if not text.recipients: raise Fault(Code.BAD_REQUEST, reason="sms.to")
        if not (text.body or text.template_name): raise Fault(Code.BAD_REQUEST, reason="sms.body")
        if text.body and not text.template_name: self.require("text")

        for feature in text.features(): self.require(feature)

    def prepare ( self, text: Text, sender: str ) -> dict[str, Any]:

        return { "from": text.sender or sender, **text.dump() }

    async def send ( self, text: Text, sender: str ) -> Receipt:

        found = [await self.deliver(text, number, text.sender or sender) for number in text.recipients]
        ids   = [str(item.get("id", "")) for item in found]

        return Receipt(
            provider=self.name, id=",".join(ids), status=str(found[-1].get("status", "queued")), to=text.recipients,
            raw={ "replies": found },
        )

    @abstractmethod
    async def deliver ( self, text: Text, number: str, sender: str ) -> dict[str, Any]: ...

class LogTexter(Texter):

    name         = "log"
    capabilities : ClassVar[frozenset[str]] = frozenset({
        "text", "template", "media", "sender", "attachments", "tags", "metadata", "silent",
    })

    def __init__ ( self, keep: int = 500 ) -> None:

        self.outbox: list[Text] = []
        self._keep  = keep

    @override
    async def send ( self, text: Text, sender: str ) -> Receipt:

        self.outbox.append(text)

        del self.outbox[:-self._keep]

        return await super().send(text, sender)

    @override
    async def deliver ( self, text: Text, number: str, sender: str ) -> dict[str, Any]:

        log.info("sms.logged", to=number, sender=sender, template=text.template_name, size=len(text.body or ""))

        return { "id": f"log-{rand.hex(6)}", "status": "logged" }

    def last ( self ) -> Text | None:

        return self.outbox[-1] if self.outbox else None

    def sent_to ( self, number: str ) -> list[Text]:

        return [text for text in self.outbox if number in text.recipients]

    def clear ( self ) -> int:

        count = len(self.outbox)

        self.outbox.clear()

        return count
