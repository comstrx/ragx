from collections.abc import Mapping
from typing import Any, ClassVar, override

from engine.json import json
from engine.net import Remote, Transport
from engine.number import Money
from .contract import Credentials, Kind, Notice, Payment, Status, Transaction
from .gateway import CAPTURE, DEPOSIT, FIND, REFUND, VOID, WEBHOOK, Gateway, headers_of

REGIONS = {
    "ARE": "https://secure.paytabs.com", "SAU": "https://secure.paytabs.sa", "EGY": "https://secure-egypt.paytabs.com",
    "OMN": "https://secure-oman.paytabs.com", "JOR": "https://secure-jordan.paytabs.com",
    "IRQ": "https://secure-iraq.paytabs.com", "GLOBAL": "https://secure-global.paytabs.com",
}
RESULTS = {
    "A": Status.PAID, "H": Status.PENDING, "P": Status.PENDING, "V": Status.VOIDED, "E": Status.FAILED,
    "D": Status.FAILED, "X": Status.FAILED, "C": Status.CANCELLED,
}
KINDS   = {
    "sale": Kind.PAYMENT, "auth": Kind.PAYMENT, "capture": Kind.CAPTURE, "refund": Kind.REFUND, "void": Kind.VOID,
}

def present ( body: Mapping[str, Any] ) -> dict[str, Any]:

    kept = { key: present(value) if isinstance(value, Mapping) else value for key, value in body.items() }

    return { key: value for key, value in kept.items() if value not in (None, {}) }

class PayTabs(Remote, Gateway):

    name         = "paytabs"
    capabilities : ClassVar[frozenset[str]] = frozenset({DEPOSIT, CAPTURE, VOID, REFUND, FIND, WEBHOOK})

    def __init__ ( self, credentials: Credentials, wait: float = 20.0, transport: Transport | None = None ) -> None:

        Gateway.__init__(self, credentials)
        base = credentials.base_url or REGIONS.get(credentials.region.upper(), REGIONS["GLOBAL"])

        Remote.__init__(self, base, wait, 2, transport)

        self.missing(("secret_key", credentials.secret_key), ("form_id", credentials.form_id))

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": self.credentials.secret_key }

    def profile ( self ) -> int | str:

        found = self.credentials.form_id

        return int(found) if found.isdigit() else found

    async def ask ( self, action: str, body: Mapping[str, Any], key: str | None = None ) -> Any:

        sent = present({ "profile_id": self.profile(), **body })

        return await self.call("POST", "/payment/request", action, json=sent, key=key)

    @override
    async def deposit ( self, payment: Payment ) -> Transaction:

        customer = payment.customer
        body     = {
            "tran_type": "sale" if payment.capture else "auth", "tran_class": "ecom", "cart_id": payment.reference,
            "cart_currency": payment.amount.currency, "cart_amount": float(payment.amount.amount),
            "cart_description": payment.description or payment.reference, "callback": payment.notify_url or None,
            "return": payment.return_url or None, "hide_shipping": True,
            "customer_details": {
                "name": customer.name or None, "email": customer.email or None, "phone": customer.phone or None,
                "country": customer.country or None, "city": customer.city or None, "street1": customer.address or None,
                "zip": customer.zip or None, "ip": customer.ip or None,
            },
        }

        return self.read(await self.ask("deposit", body, payment.key), payment.amount)

    async def follow (
        self, kind: str, key: str, amount: Money | None, note: str, idempotency: str | None,
    ) -> Transaction:

        known = await self.find(key)
        sent  = amount or known.amount
        body  = {
            "tran_type": kind, "tran_class": "ecom", "tran_ref": key, "cart_id": known.reference or key,
            "cart_currency": sent.currency, "cart_amount": float(sent.amount), "cart_description": note or kind,
        }

        return self.read({ **(await self.ask(kind, body, idempotency)), "parent": key }, sent)

    @override
    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        return await self.follow("capture", key, amount, "capture", idempotency)

    @override
    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        return await self.follow("void", key, None, "void", idempotency)

    @override
    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        return await self.follow("refund", key, amount, reason or "refund", idempotency)

    @override
    async def find ( self, key: str ) -> Transaction:

        asked = { "profile_id": self.profile(), "tran_ref": key }
        found = await self.call("POST", "/payment/query", "find", json=asked)

        return self.read(found)

    @override
    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        secret = self.credentials.webhook_secret or self.credentials.secret_key

        self.signed(secret, body, headers_of(headers).get("signature", ""))

        found = json.loads(body)
        made  = self.read(found)

        return self.notice(made.id, f"payment.{made.status.value}", made, found)

    def read ( self, found: Mapping[str, Any], fallback: Money | None = None ) -> Transaction:

        result   = found.get("payment_result") or {}
        kind     = KINDS.get(str(found.get("tran_type", "sale")).lower(), Kind.PAYMENT)
        backup   = fallback.currency if fallback else "USD"
        currency = str(found.get("cart_currency") or found.get("tran_currency") or backup)
        total    = found.get("tran_total") or found.get("cart_amount")
        amount   = self.money(total, currency) if total not in (None, "") else fallback or Money.zero(currency)
        waiting  = Status.ACTION if found.get("redirect_url") else Status.PENDING
        status   = RESULTS.get(str(result.get("response_status", "")), waiting)
        info     = found.get("payment_info") or {}
        customer = found.get("customer_details") or {}

        if kind is Kind.REFUND and status is Status.PAID: status = Status.REFUNDED
        if str(found.get("tran_type", "")).lower() == "auth" and status is Status.PAID: status = Status.AUTHORIZED

        return self.transaction(
            id=str(found.get("tran_ref", "")), kind=kind, status=status, amount=amount, total_amount=amount,
            reference=str(found.get("cart_id") or ""), parent_id=found.get("parent") or found.get("previous_tran_ref"),
            redirect_url=found.get("redirect_url"), method=info.get("payment_method"),
            card_brand=info.get("card_scheme"), card_last4=str(info.get("payment_description", ""))[-4:] or None,
            customer_email=customer.get("email"), error_code=str(result.get("response_code") or "") or None,
            error_message=result.get("response_message") if status is Status.FAILED else None,
            created_at=result.get("transaction_time"), raw=dict(found),
        )
