from collections.abc import Mapping
from typing import Any, ClassVar, override

from core.date import date
from core.json import json
from core.net import Remote, Transport
from core.number import Money
from .contract import Credentials, Kind, Notice, Payment, Status, Transaction
from .gateway import CAPTURE, DEPOSIT, FIND, REFUND, VOID, WEBHOOK, Gateway

TOKEN   = 3000.0
REGIONS = {
    "EGY": "https://accept.paymob.com", "SAU": "https://ksa.paymob.com", "ARE": "https://uae.paymob.com",
    "OMN": "https://oman.paymob.com",
}
SIGNED  = (
    "amount_cents", "created_at", "currency", "error_occured", "has_parent_transaction", "id", "integration_id",
    "is_3d_secure", "is_auth", "is_capture", "is_refunded", "is_standalone_payment", "is_voided", "order.id", "owner",
    "pending", "source_data.pan", "source_data.sub_type", "source_data.type", "success",
)

def flat ( value: object ) -> str:

    if isinstance(value, bool): return "true" if value else "false"

    return "" if value is None else str(value)

def pick ( found: Mapping[str, Any], path: str ) -> object:

    current: object = found

    for part in path.split("."):

        current = current.get(part) if isinstance(current, Mapping) else None

    if current is None and "." in path: return found.get(path.replace(".", "_"))

    return current

class Paymob(Remote, Gateway):

    name         = "paymob"
    capabilities : ClassVar[frozenset[str]] = frozenset({DEPOSIT, CAPTURE, VOID, REFUND, FIND, WEBHOOK})

    def __init__ ( self, credentials: Credentials, wait: float = 20.0, transport: Transport | None = None ) -> None:

        Gateway.__init__(self, credentials)
        base = credentials.base_url or REGIONS.get(credentials.region.upper(), REGIONS["EGY"])

        Remote.__init__(self, base, wait, 2, transport)

        self.missing(("secret_key", credentials.secret_key), ("public_key", credentials.public_key))

        self._token   = ""
        self._expires = 0.0

    async def bearer ( self ) -> str:

        if self._token and date.stamp() < self._expires: return self._token

        self.missing(("api_key", self.credentials.api_key))

        body  = { "api_key": self.credentials.api_key }
        found = await self.call("POST", "/api/auth/tokens", "auth", json=body, headers={ "authorization": "" })

        self._token   = str(found.get("token", ""))
        self._expires = date.stamp() + TOKEN

        return self._token

    def numbered ( self, key: str ) -> int | str:

        return int(key) if key.isdigit() else key

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Token {self.credentials.secret_key}" }

    def methods ( self, payment: Payment ) -> list[int | str]:

        chosen = payment.methods or tuple(part.strip() for part in self.credentials.form_id.split(",") if part.strip())

        return [int(item) if item.isdigit() else item for item in chosen]

    @override
    async def deposit ( self, payment: Payment ) -> Transaction:

        customer = payment.customer
        billing  = {
            "first_name": customer.first_name(), "last_name": customer.last_name(), "email": customer.email or "NA",
            "phone_number": customer.phone or "NA", "country": customer.country or "NA", "city": customer.city or "NA",
            "street": customer.address or "NA", "building": "NA", "floor": "NA", "apartment": "NA",
        }
        item     = { "name": payment.description or payment.reference, "amount": payment.amount.minor(), "quantity": 1 }
        body     = {
            "amount": payment.amount.minor(), "currency": payment.amount.currency,
            "payment_methods": self.methods(payment), "items": [item],
            "billing_data": billing, "special_reference": payment.reference, "extras": dict(payment.metadata),
            "notification_url": payment.notify_url or None, "redirection_url": payment.return_url or None,
        }
        found    = await self.call("POST", "/v1/intention/", "deposit", json=body, key=payment.key)
        secret   = str(found.get("client_secret", ""))
        checkout = f"{self._base}/unifiedcheckout/?publicKey={self.credentials.public_key}&clientSecret={secret}"

        return self.transaction(
            id=str(found.get("id", "")), status=Status.ACTION, amount=payment.amount, total_amount=payment.amount,
            reference=payment.reference, redirect_url=checkout, client_secret=secret, raw=dict(found),
        )

    @override
    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        sent  = amount or (await self.find(key)).amount
        body  = { "transaction_id": self.numbered(key), "amount_cents": sent.minor() }
        found = await self.call("POST", "/api/acceptance/capture", "capture", json=body, key=idempotency)

        return self.read(found, Kind.CAPTURE)

    @override
    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        body  = { "transaction_id": self.numbered(key) }
        found = await self.call("POST", "/api/acceptance/void_refund/void", "void", json=body, key=idempotency)

        return self.read(found, Kind.VOID)

    @override
    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        sent  = amount or (await self.find(key)).amount
        body  = { "transaction_id": self.numbered(key), "amount_cents": sent.minor() }
        found = await self.call("POST", "/api/acceptance/void_refund/refund", "refund", json=body, key=idempotency)

        return self.read(found, Kind.REFUND)

    @override
    async def find ( self, key: str ) -> Transaction:

        token = { "authorization": f"Bearer {await self.bearer()}" }

        return self.read(await self.call("GET", f"/api/acceptance/transactions/{key}", "find", headers=token))

    @override
    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        parsed = json.loads(body) if body else dict(query or {})
        found  = dict(parsed) if isinstance(parsed, Mapping) else {}
        held   = found.get("obj", found)
        inner  = dict(held) if isinstance(held, Mapping) else {}
        text  = "".join(flat(pick(inner, path)) for path in SIGNED)

        self.signed(self.credentials.webhook_secret, text, (query or {}).get("hmac", ""), "sha512")

        made = self.read(inner)

        return self.notice(made.id, str(found.get("type", "TRANSACTION")), made, dict(found))

    def read ( self, found: Mapping[str, Any], kind: Kind = Kind.PAYMENT ) -> Transaction:

        currency = str(found.get("currency") or "EGP")
        amount   = self.money(found.get("amount_cents"), currency, minor=True)
        refunded = int(found.get("refunded_amount_cents") or 0)
        source   = found.get("source_data") or {}
        order    = found.get("order") or {}
        status   = self.status(found, refunded, amount)

        if kind is Kind.REFUND and found.get("success"): status = Status.REFUNDED

        return self.transaction(
            id=str(found.get("id", "")), kind=kind, status=status, amount=amount, total_amount=amount,
            reference=str(order.get("merchant_order_id") or found.get("merchant_order_id") or ""),
            captured_amount=self.maybe(found.get("captured_amount"), currency, minor=True),
            refunded_amount=self.money(refunded, currency, minor=True), method=source.get("type"),
            card_brand=source.get("sub_type"), card_last4=str(source.get("pan") or "")[-4:] or None,
            parent_id=str(found.get("parent_transaction") or "") or None,
            error_message=(found.get("data") or {}).get("message") if status is Status.FAILED else None,
            created_at=found.get("created_at"), raw=dict(found),
        )

    def status ( self, found: Mapping[str, Any], refunded: int, amount: Money ) -> Status:

        if found.get("is_voided"): return Status.VOIDED
        if found.get("is_refunded") or refunded:
            return Status.REFUNDED if refunded >= amount.minor() else Status.PARTIALLY_REFUNDED
        if found.get("pending"): return Status.PENDING
        if not found.get("success"): return Status.FAILED

        return Status.AUTHORIZED if found.get("is_auth") and not found.get("is_capture") else Status.PAID
