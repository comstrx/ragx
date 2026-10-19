from collections.abc import Mapping
from typing import Any, ClassVar, override

from core.adapter import Remote
from core.date import date
from core.error import Code
from core.json import json
from core.net import Transport
from core.number import Money
from .contract import Credentials, Kind, Notice, Payment, Payout, Status, Transaction
from .gateway import EVERY, Gateway, headers_of
from .wire import form, mapping, stamped

BASE      = "https://api.stripe.com"
TOLERANCE = 300
INTENTS   = {
    "requires_payment_method": Status.PENDING, "requires_confirmation": Status.PENDING,
    "requires_action": Status.ACTION, "processing": Status.PENDING, "requires_capture": Status.AUTHORIZED,
    "succeeded": Status.PAID, "canceled": Status.CANCELLED,
}
REFUNDS   = {
    "succeeded": Status.REFUNDED, "pending": Status.PENDING, "failed": Status.FAILED, "canceled": Status.CANCELLED,
}
PAYOUTS   = {
    "paid": Status.PAID, "pending": Status.PENDING, "in_transit": Status.PENDING, "canceled": Status.CANCELLED,
}
EXPAND    = "latest_charge.balance_transaction"

class Stripe(Remote, Gateway):

    name         = "stripe"
    idempotency  : ClassVar[str] = "Idempotency-Key"
    capabilities : ClassVar[frozenset[str]] = EVERY

    def __init__ ( self, credentials: Credentials, wait: float = 20.0, transport: Transport | None = None ) -> None:

        Gateway.__init__(self, credentials)
        Remote.__init__(self, credentials.base_url or BASE, wait, 2, transport)

        self.missing(("secret_key", credentials.secret_key))

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self.credentials.secret_key}" }

    @override
    async def deposit ( self, payment: Payment ) -> Transaction:

        amount  = payment.amount
        shared  = { "metadata": { "reference": payment.reference, **payment.metadata } }
        capture = "automatic" if payment.capture else "manual"

        if not payment.return_url:

            body = {
                "amount": amount.minor(), "currency": amount.currency.lower(), "capture_method": capture,
                "automatic_payment_methods": { "enabled": True }, "description": payment.description or None,
                "receipt_email": payment.customer.email or None, **shared,
            }

            made = await self.call("POST", "/v1/payment_intents", "deposit", data=form(body), key=payment.key)

            return self.intent(made)

        line: dict[str, object] = {
            "price_data": {
                "currency": amount.currency.lower(), "unit_amount": amount.minor(),
                "product_data": { "name": payment.description or payment.reference },
            },
            "quantity": 1,
        }
        checkout: dict[str, object] = {
            "mode": "payment", "line_items": [line], "success_url": payment.return_url,
            "cancel_url": payment.cancel_url or payment.return_url, "client_reference_id": payment.reference,
            "customer_email": payment.customer.email or None,
            "payment_intent_data": { "capture_method": capture, **shared }, **shared,
        }

        made = await self.call("POST", "/v1/checkout/sessions", "deposit", data=form(checkout), key=payment.key)

        return self.session(made)

    @override
    async def find ( self, key: str ) -> Transaction:

        if key.startswith("cs_"):

            expand = { "expand[]": "payment_intent" }
            found  = await self.call("GET", f"/v1/checkout/sessions/{key}", "find", params=expand)

            return self.session(found)

        if key.startswith("re_"): return self.refunded(await self.call("GET", f"/v1/refunds/{key}", "find"))
        if key.startswith("po_"): return self.payout(await self.call("GET", f"/v1/payouts/{key}", "find"))
        if key.startswith("tr_"): return self.moved(await self.call("GET", f"/v1/transfers/{key}", "find"))

        return self.intent(await self.call("GET", f"/v1/payment_intents/{key}", "find", params={ "expand[]": EXPAND }))

    async def intent_of ( self, key: str ) -> str:

        if not key.startswith("cs_"): return key

        found = await self.call("GET", f"/v1/checkout/sessions/{key}", "find")
        inner = found.get("payment_intent")

        if not inner: raise self.fault(Code.CONFLICT, "intent.missing")

        return str(inner["id"] if isinstance(inner, Mapping) else inner)

    @override
    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        body  = { "amount_to_capture": amount.minor() } if amount else {}
        path  = f"/v1/payment_intents/{await self.intent_of(key)}/capture"
        found = await self.call("POST", path, "capture", data=form(body), key=idempotency)

        return self.intent(found, Kind.CAPTURE)

    @override
    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        path  = f"/v1/payment_intents/{await self.intent_of(key)}/cancel"
        found = await self.call("POST", path, "void", key=idempotency)

        return self.intent(found, Kind.VOID)

    @override
    async def cancel ( self, key: str, idempotency: str | None = None ) -> Transaction:

        if not key.startswith("cs_"): return await self.void(key, idempotency)

        return self.session(await self.call("POST", f"/v1/checkout/sessions/{key}/expire", "cancel", key=idempotency))

    @override
    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        body: dict[str, object] = {
            "payment_intent": await self.intent_of(key), "amount": amount.minor() if amount else None,
        }

        if reason: body["metadata"] = { "reason": reason }

        return self.refunded(await self.call("POST", "/v1/refunds", "refund", data=form(body), key=idempotency))

    @override
    async def withdraw ( self, payout: Payout ) -> Transaction:

        body = {
            "amount": payout.amount.minor(), "currency": payout.amount.currency.lower(),
            "description": payout.note or None, "metadata": { "reference": payout.reference, **payout.metadata },
        }

        return self.payout(await self.call("POST", "/v1/payouts", "withdraw", data=form(body), key=payout.key))

    @override
    async def transfer (
        self, amount: Money, destination: str, reference: str = "", idempotency: str | None = None,
    ) -> Transaction:

        body = {
            "amount": amount.minor(), "currency": amount.currency.lower(), "destination": destination,
            "transfer_group": reference or None, "metadata": { "reference": reference },
        }

        return self.moved(await self.call("POST", "/v1/transfers", "transfer", data=form(body), key=idempotency))

    @override
    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        header = headers_of(headers).get("stripe-signature", "")
        given  = dict(part.split("=", 1) for part in header.split(",") if "=" in part)
        stamp  = given.get("t", "")
        stale  = not stamp.isdigit() or abs(date.stamp() - int(stamp)) > TOLERANCE

        if stale: raise self.fault(Code.UNAUTHORIZED, "webhook.stale")

        self.signed(self.credentials.webhook_secret, f"{stamp}.".encode() + body, given.get("v1", ""))

        event = json.loads(body)
        found = event.get("data", {}).get("object", {})

        return self.notice(str(event.get("id", "")), str(event.get("type", "")), self.object(found), event)

    def object ( self, found: Mapping[str, Any] ) -> Transaction | None:

        match found.get("object"):
            case "checkout.session": return self.session(found)
            case "payment_intent": return self.intent(found)
            case "refund": return self.refunded(found)
            case "payout": return self.payout(found)
            case "transfer": return self.moved(found)
            case _: return None

    def intent ( self, found: Mapping[str, Any], kind: Kind = Kind.PAYMENT ) -> Transaction:

        currency = str(found.get("currency", "usd")).upper()
        charge   = mapping(found.get("latest_charge"))
        balance  = mapping(charge.get("balance_transaction"))
        card     = mapping(mapping(charge.get("payment_method_details")).get("card"))
        refunded = int(charge.get("amount_refunded", 0) or 0)
        status   = INTENTS.get(str(found.get("status")), Status.PENDING)
        failed   = found.get("last_payment_error") or {}

        if refunded and status is Status.PAID:
            status = Status.REFUNDED if refunded >= int(found.get("amount", 0)) else Status.PARTIALLY_REFUNDED
        if failed and status is Status.PENDING: status = Status.FAILED

        return self.transaction(
            id=str(found.get("id", "")), kind=kind, status=status,
            amount=self.money(found.get("amount"), currency, minor=True),
            reference=str((found.get("metadata") or {}).get("reference", "")),
            total_amount=self.maybe(found.get("amount"), currency, minor=True),
            captured_amount=self.maybe(found.get("amount_received"), currency, minor=True),
            gross_amount=self.maybe(balance.get("amount"), currency, minor=True),
            fee_amount=self.maybe(balance.get("fee"), currency, minor=True),
            net_amount=self.maybe(balance.get("net"), currency, minor=True),
            refunded_amount=self.money(refunded, currency, minor=True),
            card_brand=card.get("brand"), card_last4=card.get("last4"), method="card" if card else None,
            client_secret=found.get("client_secret"), error_code=failed.get("code"),
            error_message=failed.get("message"),
            created_at=stamped(found.get("created")), raw=dict(found),
        )

    def session ( self, found: Mapping[str, Any] ) -> Transaction:

        currency = str(found.get("currency", "usd")).upper()
        inner    = found.get("payment_intent")
        paid     = found.get("payment_status") == "paid"
        status   = Status.PAID if paid else Status.CANCELLED if found.get("status") == "expired" else Status.ACTION

        if isinstance(inner, Mapping) and paid: status = self.intent(inner).status

        return self.transaction(
            id=str(found.get("id", "")), status=status,
            amount=self.money(found.get("amount_total"), currency, minor=True),
            reference=str(found.get("client_reference_id") or ""), redirect_url=found.get("url"),
            total_amount=self.maybe(found.get("amount_total"), currency, minor=True),
            customer_email=(found.get("customer_details") or {}).get("email") or found.get("customer_email"),
            created_at=stamped(found.get("created")), raw=dict(found),
        )

    def refunded ( self, found: Mapping[str, Any] ) -> Transaction:

        currency = str(found.get("currency", "usd")).upper()

        return self.transaction(
            id=str(found.get("id", "")), kind=Kind.REFUND, status=REFUNDS.get(str(found.get("status")), Status.PENDING),
            amount=self.money(found.get("amount"), currency, minor=True), parent_id=found.get("payment_intent"),
            refunded_amount=self.money(found.get("amount"), currency, minor=True),
            created_at=stamped(found.get("created")),
            raw=dict(found),
        )

    def payout ( self, found: Mapping[str, Any] ) -> Transaction:

        currency = str(found.get("currency", "usd")).upper()
        status   = PAYOUTS.get(str(found.get("status")), Status.FAILED)

        return self.transaction(
            id=str(found.get("id", "")), kind=Kind.PAYOUT, status=status,
            amount=self.money(found.get("amount"), currency, minor=True),
            reference=str((found.get("metadata") or {}).get("reference", "")), error_code=found.get("failure_code"),
            error_message=found.get("failure_message"), created_at=stamped(found.get("created")), raw=dict(found),
        )

    def moved ( self, found: Mapping[str, Any] ) -> Transaction:

        currency = str(found.get("currency", "usd")).upper()
        status   = Status.CANCELLED if found.get("reversed") else Status.PAID

        return self.transaction(
            id=str(found.get("id", "")), kind=Kind.TRANSFER, status=status,
            amount=self.money(found.get("amount"), currency, minor=True),
            reference=str(found.get("transfer_group") or ""),
            created_at=stamped(found.get("created")), raw=dict(found),
        )
