from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, Self

from core.adapter import Manager
from core.error import Code, Fault
from core.log import log
from core.net import Transport
from core.number import Money
from .contract import Credentials, Customer, Notice, Payment, Payout, Transaction
from .gateway import CAPTURE, CANCEL, DEPOSIT, FIND, REFUND, TRANSFER, VOID, WEBHOOK, WITHDRAW, Gateway
from .paymob import Paymob
from .paypal import PayPal
from .paytabs import PayTabs
from .sandbox import Sandbox
from .stripe import Stripe

type Factory = Callable[[Credentials, Transport | None], Gateway]

FACTORIES: dict[str, Factory] = {
    "stripe"  : lambda credentials, transport: Stripe(credentials, transport=transport),
    "paypal"  : lambda credentials, transport: PayPal(credentials, transport=transport),
    "paytabs" : lambda credentials, transport: PayTabs(credentials, transport=transport),
    "paymob"  : lambda credentials, transport: Paymob(credentials, transport=transport),
    "sandbox" : lambda credentials, _: Sandbox(credentials),
}

class Charge:

    __slots__ = ("_owner", "_payment", "_using")

    def __init__ ( self, owner: Payments, payment: Payment, using: str | None = None ) -> None:

        self._owner   = owner
        self._payment = payment
        self._using   = using

    def change ( self, **values: Any ) -> Self:

        return type(self)(self._owner, replace(self._payment, **values), self._using)

    def customer ( self, name: str = "", email: str = "", phone: str = "", **more: str ) -> Self:

        return self.change(customer=Customer(name=name, email=email, phone=phone, **more))

    def describe ( self, text: str ) -> Self:

        return self.change(description=text)

    def returns ( self, success: str, cancel: str = "" ) -> Self:

        return self.change(return_url=success, cancel_url=cancel or success)

    def notify ( self, url: str ) -> Self:

        return self.change(notify_url=url)

    def authorize ( self ) -> Self:

        return self.change(capture=False)

    def methods ( self, *names: str ) -> Self:

        return self.change(methods=names)

    def meta ( self, **values: str ) -> Self:

        return self.change(metadata={ **self._payment.metadata, **values })

    def idempotent ( self, key: str ) -> Self:

        return self.change(key=key)

    def via ( self, provider: str ) -> Self:

        return type(self)(self._owner, self._payment, provider)

    def payment ( self ) -> Payment:

        return self._payment

    async def deposit ( self ) -> Transaction:

        return await self._owner.deposit(self._payment, self._using)

class Payments(Manager[Gateway]):

    def __init__ ( self ) -> None:

        super().__init__("gateway")

        self._factories = dict(FACTORIES)

    def extend ( self, name: str, factory: Factory ) -> None:

        self._factories[name] = factory

    def build (
        self, name: str, credentials: Credentials | Mapping[str, Any], transport: Transport | None = None,
    ) -> Gateway:

        chosen = credentials if isinstance(credentials, Credentials) else Credentials.of(credentials)
        maker  = self._factories.get(name)

        if maker is None: raise Fault(Code.INTERNAL, reason=f"gateway.{name}.missing")

        return maker(chosen, transport)

    def connect (
        self, name: str, credentials: Credentials | Mapping[str, Any], transport: Transport | None = None,
        default: bool = False,
    ) -> Gateway:

        return self.register(self.build(name, credentials, transport), default)

    def charge ( self, amount: Money | str | float, currency: str = "USD", reference: str = "" ) -> Charge:

        money = amount if isinstance(amount, Money) else Money.of(amount, currency)

        return Charge(self, Payment(amount=money, reference=reference))

    def chosen ( self, capability: str, using: str | None ) -> Gateway:

        adapter = self.use(using)

        adapter.require(capability)

        return adapter

    async def deposit ( self, payment: Payment, using: str | None = None ) -> Transaction:

        made = await self.chosen(DEPOSIT, using).deposit(payment)

        log.info("gateway.deposit", provider=made.provider, reference=payment.reference, status=made.status.value)

        return made

    async def capture (
        self, key: str, amount: Money | None = None, using: str | None = None, idempotency: str | None = None,
    ) -> Transaction:

        return await self.chosen(CAPTURE, using).capture(key, amount, idempotency)

    async def void ( self, key: str, using: str | None = None, idempotency: str | None = None ) -> Transaction:

        return await self.chosen(VOID, using).void(key, idempotency)

    async def reject ( self, key: str, using: str | None = None, idempotency: str | None = None ) -> Transaction:

        return await self.void(key, using, idempotency)

    async def cancel ( self, key: str, using: str | None = None, idempotency: str | None = None ) -> Transaction:

        return await self.chosen(CANCEL, using).cancel(key, idempotency)

    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", using: str | None = None,
        idempotency: str | None = None,
    ) -> Transaction:

        made = await self.chosen(REFUND, using).refund(key, amount, reason, idempotency)

        log.info("gateway.refund", provider=made.provider, parent=key, status=made.status.value)

        return made

    async def withdraw ( self, payout: Payout, using: str | None = None ) -> Transaction:

        made = await self.chosen(WITHDRAW, using).withdraw(payout)

        log.info("gateway.withdraw", provider=made.provider, reference=payout.reference, status=made.status.value)

        return made

    async def transfer (
        self, amount: Money, destination: str, reference: str = "", using: str | None = None,
        idempotency: str | None = None,
    ) -> Transaction:

        return await self.chosen(TRANSFER, using).transfer(amount, destination, reference, idempotency)

    async def find ( self, key: str, using: str | None = None ) -> Transaction:

        return await self.chosen(FIND, using).find(key)

    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None, using: str | None = None,
    ) -> Notice:

        notice = await self.chosen(WEBHOOK, using).webhook(body, headers, query)

        log.info("gateway.webhook", provider=notice.provider, type=notice.type, id=notice.id)

        return notice
