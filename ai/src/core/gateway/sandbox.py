from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import ClassVar, override

from core.crypto import crypto
from core.date import date
from core.error import Code, Fault
from core.json import json
from core.number import Money
from core.rand import rand
from .contract import Credentials, Kind, Notice, Payment, Payout, Status, Transaction
from .gateway import EVERY, Gateway, headers_of

RATE   = Decimal("0.029")
FIXED  = Decimal("0.30")
HEADER = "x-sandbox-signature"
PAGE   = "https://sandbox.local/pay"

class Sandbox(Gateway):

    name         = "sandbox"
    capabilities : ClassVar[frozenset[str]] = EVERY

    def __init__ ( self, credentials: Credentials | None = None ) -> None:

        super().__init__(credentials or Credentials(webhook_secret=rand.token(24), sandbox=True))

        self._kept: dict[str, Transaction] = {}
        self._keys: dict[str, str] = {}

    def remember ( self, made: Transaction, key: str | None = None ) -> Transaction:

        self._kept[made.id] = made

        if key: self._keys[key] = made.id

        return made

    def replay ( self, key: str | None ) -> Transaction | None:

        return self._kept.get(self._keys.get(key or "", ""))

    def fees ( self, amount: Money ) -> tuple[Money, Money]:

        fee = Money.of(amount.amount * RATE + FIXED, amount.currency)

        return fee, amount.sub(fee)

    @override
    async def deposit ( self, payment: Payment ) -> Transaction:

        known = self.replay(payment.key)

        if known is not None: return known

        key      = f"sb_{rand.hex(8)}"
        declined = "decline" in payment.reference
        status   = Status.FAILED if declined else Status.ACTION if payment.return_url else Status.PENDING
        made     = self.transaction(
            id=key, status=status, amount=payment.amount, total_amount=payment.amount, reference=payment.reference,
            redirect_url=f"{PAGE}/{key}" if payment.return_url else None, client_secret=f"{key}_secret",
            customer_email=payment.customer.email or None, error_code="card_declined" if declined else None,
            created_at=date.iso(date.now()), raw={ "capture": payment.capture, "metadata": dict(payment.metadata) },
        )

        if not declined and not payment.return_url: made = self.settle(made)

        return self.remember(made, payment.key)

    def settle ( self, made: Transaction ) -> Transaction:

        if made.raw.get("capture", True) is False: return replace(made, status=Status.AUTHORIZED)

        fee, net = self.fees(made.amount)

        return replace(
            made, status=Status.PAID, captured_amount=made.amount, gross_amount=made.amount, fee_amount=fee,
            net_amount=net, method="card", card_brand="visa", card_last4="4242",
        )

    def pay ( self, key: str ) -> Transaction:

        made = self.known(key)

        if made.status is not Status.ACTION: raise Fault(Code.CONFLICT, reason="gateway.sandbox.pay")

        return self.remember(self.settle(made))

    def known ( self, key: str ) -> Transaction:

        found = self._kept.get(key)

        if found is None: raise self.fault(Code.NOT_FOUND, "find")

        return found

    @override
    async def find ( self, key: str ) -> Transaction:

        return self.known(key)

    @override
    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        made = self.known(key)

        if made.status is not Status.AUTHORIZED: raise self.fault(Code.CONFLICT, "capture.state")

        taken    = amount or made.amount
        fee, net = self.fees(taken)
        done     = replace(
            made, kind=Kind.CAPTURE, status=Status.PAID, captured_amount=taken, gross_amount=taken, fee_amount=fee,
            net_amount=net,
        )

        return self.remember(done)

    @override
    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        made = self.known(key)

        if made.status is not Status.AUTHORIZED: raise self.fault(Code.CONFLICT, "void.state")

        return self.remember(replace(made, kind=Kind.VOID, status=Status.VOIDED))

    @override
    async def cancel ( self, key: str, idempotency: str | None = None ) -> Transaction:

        made = self.known(key)

        if made.status not in (Status.ACTION, Status.PENDING): raise self.fault(Code.CONFLICT, "cancel.state")

        return self.remember(replace(made, status=Status.CANCELLED))

    @override
    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        known = self.replay(idempotency)

        if known is not None: return known

        made  = self.known(key)
        taken = amount or made.amount
        total = (made.refunded_amount or Money.zero(made.currency())).add(taken)

        if not made.status.settled() or made.amount < total: raise self.fault(Code.CONFLICT, "refund.state")

        whole  = total.amount >= made.amount.amount
        parent = replace(made, status=Status.REFUNDED if whole else Status.PARTIALLY_REFUNDED, refunded_amount=total)
        back   = self.transaction(
            id=f"rf_{rand.hex(8)}", kind=Kind.REFUND, status=Status.REFUNDED, amount=taken, refunded_amount=taken,
            parent_id=key, reference=made.reference, created_at=date.iso(date.now()), raw={ "reason": reason },
        )

        self.remember(parent)

        return self.remember(back, idempotency)

    @override
    async def withdraw ( self, payout: Payout ) -> Transaction:

        known = self.replay(payout.key)

        if known is not None: return known

        made = self.transaction(
            id=f"po_{rand.hex(8)}", kind=Kind.PAYOUT, status=Status.PAID, amount=payout.amount,
            reference=payout.reference,
            created_at=date.iso(date.now()), raw={ "recipient": payout.recipient, "channel": payout.channel },
        )

        return self.remember(made, payout.key)

    @override
    async def transfer (
        self, amount: Money, destination: str, reference: str = "", idempotency: str | None = None,
    ) -> Transaction:

        known = self.replay(idempotency)

        if known is not None: return known

        made = self.transaction(
            id=f"tr_{rand.hex(8)}", kind=Kind.TRANSFER, status=Status.PAID, amount=amount, reference=reference,
            created_at=date.iso(date.now()), raw={ "destination": destination },
        )

        return self.remember(made, idempotency)

    def sign ( self, body: bytes ) -> dict[str, str]:

        return { HEADER: crypto.sign(body, self.credentials.webhook_secret) }

    @override
    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        self.signed(self.credentials.webhook_secret, body, headers_of(headers).get(HEADER, ""))

        event = json.loads(body)
        made  = self._kept.get(str(event.get("transaction", "")))

        return self.notice(str(event.get("id", "")), str(event.get("type", "")), made, dict(event))
