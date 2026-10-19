from collections.abc import Mapping
from decimal import Decimal
from typing import Any, ClassVar

from core.adapter import Adapter
from core.crypto import crypto
from core.error import Code, Fault
from core.number import Money
from .contract import Credentials, Kind, Notice, Payment, Payout, Status, Transaction

DEPOSIT  = "deposit"
CAPTURE  = "capture"
VOID     = "void"
CANCEL   = "cancel"
REFUND   = "refund"
WITHDRAW = "withdraw"
TRANSFER = "transfer"
FIND     = "find"
WEBHOOK  = "webhook"
EVERY    = frozenset({DEPOSIT, CAPTURE, VOID, CANCEL, REFUND, WITHDRAW, TRANSFER, FIND, WEBHOOK})

class Gateway(Adapter):

    family : ClassVar[str] = "gateway"

    def __init__ ( self, credentials: Credentials ) -> None:

        self.credentials = credentials

    async def deposit ( self, payment: Payment ) -> Transaction:

        raise self.unsupported(DEPOSIT)

    async def capture ( self, key: str, amount: Money | None = None, idempotency: str | None = None ) -> Transaction:

        raise self.unsupported(CAPTURE)

    async def void ( self, key: str, idempotency: str | None = None ) -> Transaction:

        raise self.unsupported(VOID)

    async def cancel ( self, key: str, idempotency: str | None = None ) -> Transaction:

        raise self.unsupported(CANCEL)

    async def refund (
        self, key: str, amount: Money | None = None, reason: str = "", idempotency: str | None = None,
    ) -> Transaction:

        raise self.unsupported(REFUND)

    async def withdraw ( self, payout: Payout ) -> Transaction:

        raise self.unsupported(WITHDRAW)

    async def transfer (
        self, amount: Money, destination: str, reference: str = "", idempotency: str | None = None,
    ) -> Transaction:

        raise self.unsupported(TRANSFER)

    async def find ( self, key: str ) -> Transaction:

        raise self.unsupported(FIND)

    async def webhook (
        self, body: bytes, headers: Mapping[str, str], query: Mapping[str, str] | None = None,
    ) -> Notice:

        raise self.unsupported(WEBHOOK)

    def money ( self, value: object, currency: str, minor: bool = False ) -> Money:

        if minor: return Money.minor_of(int(Decimal(str(value or 0))), currency)

        return Money.of(value if value not in (None, "") else 0, currency)

    def maybe ( self, value: object, currency: str, minor: bool = False ) -> Money | None:

        return None if value in (None, "") else self.money(value, currency, minor)

    def signed ( self, secret: str, payload: bytes | str, given: str, algorithm: str = "sha256" ) -> None:

        if not secret: raise self.fault(Code.INTERNAL, "config.webhook_secret")
        if not given or not crypto.compare(crypto.sign(payload, secret, algorithm), given.strip().lower()):
            raise self.fault(Code.UNAUTHORIZED, "webhook.signature")

    def transaction ( self, **values: Any ) -> Transaction:

        kind   = values.pop("kind", Kind.PAYMENT)
        status = values.pop("status", Status.PENDING)

        return Transaction(provider=self.name, kind=kind, status=status, test=self.credentials.sandbox, **values)

    def notice ( self, key: str, kind: str, transaction: Transaction | None, raw: dict[str, Any] ) -> Notice:

        return Notice(provider=self.name, id=key, type=kind, transaction=transaction, raw=raw)

def headers_of ( headers: Mapping[str, str] ) -> dict[str, str]:

    return { name.lower(): value for name, value in headers.items() }

def failure ( reason: str ) -> Fault:

    return Fault(Code.BAD_REQUEST, reason=reason)
