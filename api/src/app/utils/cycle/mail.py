from collections.abc import Mapping
from typing import Any, ClassVar, Self, override

from core.error import Code, Fault
from core.mail import Attachment, Message, mail
from core.queue import Queued, queue
from core.string import string
from core.view import view

class Mail:

    registry : ClassVar[dict[str, type[Mail]]] = {}
    subject  : str = ""
    html     : str = ""
    text     : str = ""

    @override
    def __init_subclass__ ( cls, **kwargs: object ) -> None:

        super().__init_subclass__(**kwargs)

        Mail.registry[cls.name()] = cls

    def __init__ ( self, **data: object ) -> None:

        self._data: dict[str, object] = dict(data)
        self._to: list[str] = []
        self._cc: list[str] = []
        self._bcc: list[str] = []
        self._reply_to: str | None = None
        self._attachments: list[Attachment] = []

    @classmethod
    def name ( cls ) -> str:

        return f"{cls.__module__}:{cls.__qualname__}"

    def to ( self, *emails: str ) -> Self:

        self._to.extend(emails)

        return self

    def cc ( self, *emails: str ) -> Self:

        self._cc.extend(emails)

        return self

    def bcc ( self, *emails: str ) -> Self:

        self._bcc.extend(emails)

        return self

    def reply_to ( self, email: str ) -> Self:

        self._reply_to = email

        return self

    def with_ ( self, **data: object ) -> Self:

        self._data.update(data)

        return self

    def attach ( self, name: str, content: bytes, kind: str = "application/octet-stream" ) -> Self:

        self._attachments.append(Attachment(name, content, kind))

        return self

    def title ( self ) -> str:

        return self.subject.format_map(self._data) if self.subject else ""

    def queued ( self ) -> bool:

        return isinstance(self, Queued) and not queue.inline()

    def dump ( self ) -> dict[str, Any]:

        return {
            "data"        : self._data,
            "to"          : self._to,
            "cc"          : self._cc,
            "bcc"         : self._bcc,
            "reply_to"    : self._reply_to,
            "attachments" : [
                { "name": item.name, "type": item.type, "content": string.to_base64(item.content) }
                for item in self._attachments
            ],
        }

    @classmethod
    def load ( cls, payload: Mapping[str, Any] ) -> Self:

        built = cls(**dict(payload.get("data", {})))

        built.to(*payload.get("to", [])).cc(*payload.get("cc", [])).bcc(*payload.get("bcc", []))

        if payload.get("reply_to"): built.reply_to(str(payload["reply_to"]))

        for item in payload.get("attachments", []):
            built.attach(str(item["name"]), string.from_base64(str(item["content"])), str(item["type"]))

        return built

    async def build ( self ) -> Message:

        if not self._to: raise Fault(Code.BAD_REQUEST, reason="mail.to")
        if not (self.html or self.text): raise Fault(Code.INTERNAL, reason=f"{type(self).__name__}.view")

        message = mail.draft(self.title()).to(*self._to).cc(*self._cc).bcc(*self._bcc)

        if self.html: message = message.html(await view.render(self.html, **self._data))
        if self.text: message = message.text(await view.render(self.text, **self._data))
        if self._reply_to: message = message.reply_to(self._reply_to)

        for item in self._attachments: message = message.attach(item.name, item.content, item.type)

        return message

    async def send_now ( self ) -> Message:

        message = await self.build()

        await mail.send(message)

        return message

    async def send ( self ) -> Message | None:

        if not self.queued(): return await self.send_now()

        policy = self if isinstance(self, Queued) else Queued()

        await queue.enqueue(
            Mail.deliver, (self.name(), self.dump()),
            queue=policy.queue, delay=policy.delay, tries=policy.tries, backoff=policy.backoff,
        )

        return None

    @staticmethod
    async def deliver ( name: str, payload: Mapping[str, Any] ) -> None:

        kind = Mail.registry.get(name)

        if kind is None: raise Fault(Code.INTERNAL, reason=f"mail.{name}")

        await kind.load(payload).send_now()
