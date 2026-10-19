from collections.abc import Mapping
from typing import Any, ClassVar, override

from core.date import date
from core.error import Code
from core.json import json
from core.net import Remote, Transport
from core.number import Money
from core.string import string
from .contract import Credentials, Kind, Notice, Payment, Payout, Status, Transaction
from .gateway import CAPTURE, DEPOSIT, FIND, REFUND, VOID, WEBHOOK, WITHDRAW, Gateway, headers_of

LIVE    = "https://api-m.paypal.com"
SANDBOX = "https://api-m.sandbox.paypal.com"
MARGIN  = 60.0
ORDERS  = {
    "CREATED": Status.PENDING, "SAVED": Status.PENDING, "APPROVED": Status.AUTHORIZED,
    "PAYER_ACTION_REQUIRED": Status.ACTION, "COMPLETED": Status.PAID, "VOIDED": Status.VOIDED,
}
STATES  = {
    "COMPLETED": Status.PAID, "PENDING": Status.PENDING, "DECLINED": Status.FAILED, "FAILED": Status.FAILED,
    "REFUNDED": Status.REFUNDED, "PARTIALLY_REFUNDED": Status.PARTIALLY_REFUNDED, "CANCELLED": Status.CANCELLED,
    "CREATED": Status.AUTHORIZED, "CAPTURED": Status.PAID, "VOIDED": Status.VOIDED, "SUCCESS": Status.PAID,
    "DENIED": Status.FAILED, "PROCESSING": Status.PENDING,
}
SIGNED  = ("auth_algo", "cert_url", "transmission_id", "transmission_sig", "transmission_time")

def value_of ( amount: Money ) -> dict[str, str]:

    return { "currency_code": amount.currency, "value": str(amount.amount) }

class PayPal(Remote, Gateway):

    name         = "paypal"
    idempotency  : ClassVar[str] = "PayPal-Request-Id"
    capabilities : ClassVar[frozenset[str]] = frozenset({DEPOSIT, CAPTURE, VOID, REFUND, WITHDRAW, FIND, WEBHOOK})

    def __init__ ( self, credentials: Credentials, wait: float = 20.0, transport: Transport | None = None ) -> None:

        Gateway.__init__(self, credentials)
        Remote.__init__(self, credentials.base_url or (SANDBOX if credentials.sandbox else LIVE), wait, 2, transport)

        self.missing(("client_id", credentials.client_id), ("secret_key", credentials.secret_key))

        self._token   = ""
        self._expires = 0.0

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._token}" }

    async def login ( self ) -> None:

        if self._token and date.stamp() < self._expires: return

        basic = string.to_base64(f"{self.credentials.client_id}:{self.credentials.secret_key}")
        found = await self.call(
            "POST", "/v1/oauth2/token", "login", data={ "grant_type": "client_credentials" },
            headers={ "authorization": f"Basic {basic}" },
        )

        self._token   = str(found.get("access_token", ""))
        self._expires = date.stamp() + float(found.get("expires_in", 0)) - MARGIN

    async def ask ( self, method: str, path: str, action: str, body: object = None, key: str | None = None ) -> Any:

        await self.login()

        return await self.call(method, path, action, json=body, key=key)

    @override
    async def deposit ( self, payment: Payment ) -> Transaction:

        context = {
            "return_url": payment.return_url, "cancel_url": payment.cancel_url or payment.return_url,
            "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
        }
        unit    = {
            "reference_id": payment.reference, "custom_id": payment.reference, "amount": value_of(payment.amount),
            "description": payment.description or payment.reference,
        }
        body    = {
            "intent": "CAPTURE" if payment.capture else "AUTHORIZE", "purchase_units": [unit],
            "payment_source": { "paypal": { "experience_context": context } },
        }

        return self.order(await self.ask("POST", "/v2/checkout/orders", "deposit", body, payment.key), payment.amount)

    @override
    async def find ( self, key: str ) -> Transaction:

        return self.order(await self.ask("GET", f"/v2/checkout/orders/{key}", "find"))

    async def payments ( self, key: str ) -> dict[str, Any]:

        found = await self.ask("GET", f"/v2/checkout/orders/{key}", "find")
        units = found.get("purchase_units") or [{}]

        return dict(units[0].get("payments") or {})

    @override
    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        held = (await self.payments(key)).get("authorizations") or []

        if not held:

            done = await self.ask("POST", f"/v2/checkout/orders/{key}/capture", "capture", {}, idempotency)

            return self.order(done)

        body  = { "amount": value_of(amount), "final_capture": True } if amount else {}
        path  = f"/v2/payments/authorizations/{held[0]['id']}/capture"
        found = await self.ask("POST", path, "capture", body, idempotency)

        return self.captured(found, Kind.CAPTURE)

    @override
    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        held = (await self.payments(key)).get("authorizations") or []

        if not held: raise self.fault(Code.CONFLICT, "void.authorization")

        await self.ask("POST", f"/v2/payments/authorizations/{held[0]['id']}/void", "void", None, idempotency)

        return self.captured({ **held[0], "status": "VOIDED" }, Kind.VOID)

    @override
    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        captures = (await self.payments(key)).get("captures") or []
        target   = captures[0]["id"] if captures else key
        body: dict[str, Any] = { "amount": value_of(amount) } if amount else {}

        if reason: body["note_to_payer"] = reason

        found    = await self.ask("POST", f"/v2/payments/captures/{target}/refund", "refund", body, idempotency)

        return self.captured({ **found, "parent": target }, Kind.REFUND)

    @override
    async def withdraw ( self, payout: Payout ) -> Transaction:

        kinds = { "email": "EMAIL", "phone": "PHONE", "account": "PAYPAL_ID" }
        item  = {
            "recipient_type": kinds.get(payout.channel, "EMAIL"), "receiver": payout.recipient,
            "amount": { "value": str(payout.amount.amount), "currency": payout.amount.currency },
            "note": payout.note or payout.reference, "sender_item_id": payout.reference,
        }
        head  = { "sender_batch_id": payout.reference, "email_subject": payout.note }
        body  = { "sender_batch_header": head, "items": [item] }
        found = await self.ask("POST", "/v1/payments/payouts", "withdraw", body, payout.key)
        batch = found.get("batch_header") or {}

        return self.transaction(
            id=str(batch.get("payout_batch_id", "")), kind=Kind.PAYOUT,
            status=STATES.get(str(batch.get("batch_status")), Status.PENDING), amount=payout.amount,
            reference=payout.reference, raw=dict(found),
        )

    @override
    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        given  = headers_of(headers)
        event  = json.loads(body)
        signed = { name: given.get(f"paypal-{name.replace('_', '-')}", "") for name in SIGNED }

        if not self.credentials.webhook_id: raise self.fault(Code.INTERNAL, "config.webhook_id")
        if not all(signed.values()): raise self.fault(Code.UNAUTHORIZED, "webhook.signature")

        checked = await self.ask(
            "POST", "/v1/notifications/verify-webhook-signature", "webhook",
            { **signed, "webhook_id": self.credentials.webhook_id, "webhook_event": event },
        )

        if checked.get("verification_status") != "SUCCESS": raise self.fault(Code.UNAUTHORIZED, "webhook.signature")

        kind     = str(event.get("event_type", ""))
        resource = event.get("resource") or {}
        found    = self.order(resource) if kind.startswith("CHECKOUT.ORDER") else self.captured(resource, Kind.PAYMENT)

        return self.notice(str(event.get("id", "")), kind, found, event)

    def order ( self, found: Mapping[str, Any], fallback: Money | None = None ) -> Transaction:

        units    = found.get("purchase_units") or [{}]
        unit     = units[0]
        amount   = unit.get("amount") or {}
        captures = (unit.get("payments") or {}).get("captures") or []
        links    = { link.get("rel"): link.get("href") for link in found.get("links") or [] }
        money    = self.money(amount.get("value"), str(amount.get("currency_code", "USD"))) if amount else fallback
        status   = ORDERS.get(str(found.get("status")), Status.PENDING)

        if captures: return self.captured({ **captures[0], "reference": unit.get("reference_id"), "order": found })

        return self.transaction(
            id=str(found.get("id", "")), status=status, amount=money or Money.zero("USD"),
            reference=str(unit.get("reference_id") or ""),
            redirect_url=links.get("payer-action") or links.get("approve"),
            created_at=found.get("create_time"), raw=dict(found),
        )

    def captured ( self, found: Mapping[str, Any], kind: Kind = Kind.PAYMENT ) -> Transaction:

        amount    = found.get("amount") or {}
        currency  = str(amount.get("currency_code", "USD"))
        breakdown = found.get("seller_receivable_breakdown") or {}
        fee       = (breakdown.get("paypal_fee") or {}).get("value")
        order     = found.get("order") or {}

        return self.transaction(
            id=str(order.get("id") or found.get("id", "")), kind=kind,
            status=STATES.get(str(found.get("status")), Status.PENDING),
            amount=self.money(amount.get("value"), currency),
            reference=str(found.get("reference") or found.get("custom_id") or ""), parent_id=found.get("parent"),
            gross_amount=self.maybe((breakdown.get("gross_amount") or {}).get("value"), currency),
            fee_amount=self.maybe(fee, currency),
            net_amount=self.maybe((breakdown.get("net_amount") or {}).get("value"), currency),
            captured_amount=self.maybe(amount.get("value"), currency) if kind is not Kind.REFUND else None,
            refunded_amount=self.maybe(amount.get("value"), currency) if kind is Kind.REFUND else None,
            created_at=found.get("create_time"), raw=dict(found),
        )
