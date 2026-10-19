from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Self

from core.number import Money

class Status(StrEnum):

    PENDING            = "pending"
    ACTION             = "action"
    AUTHORIZED         = "authorized"
    PAID               = "paid"
    FAILED             = "failed"
    CANCELLED          = "cancelled"
    VOIDED             = "voided"
    REFUNDED           = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"

    def settled ( self ) -> bool:

        return self in (Status.PAID, Status.REFUNDED, Status.PARTIALLY_REFUNDED)

    def final ( self ) -> bool:

        return self not in (Status.PENDING, Status.ACTION, Status.AUTHORIZED)

    def successful ( self ) -> bool:

        return self in (Status.AUTHORIZED, Status.PAID)

class Kind(StrEnum):

    PAYMENT  = "payment"
    CAPTURE  = "capture"
    REFUND   = "refund"
    VOID     = "void"
    PAYOUT   = "payout"
    TRANSFER = "transfer"

@dataclass(frozen=True, slots=True, kw_only=True)
class Credentials:

    api_key        : str = ""
    secret_key     : str = ""
    public_key     : str = ""
    client_id      : str = ""
    form_id        : str = ""
    merchant_id    : str = ""
    webhook_id     : str = ""
    webhook_secret : str = ""
    region         : str = ""
    sandbox        : bool = False
    base_url       : str = ""

    @classmethod
    def of ( cls, values: Mapping[str, Any] ) -> Self:

        known = { name: values[name] for name in cls.__dataclass_fields__ if name in values }

        return cls(**known)

    def masked ( self ) -> dict[str, Any]:

        return {
            name: (bool(getattr(self, name)) if name.endswith(("key", "secret", "_id")) else getattr(self, name))
            for name in self.__dataclass_fields__
        }

@dataclass(frozen=True, slots=True, kw_only=True)
class Customer:

    name    : str = ""
    email   : str = ""
    phone   : str = ""
    country : str = ""
    city    : str = ""
    address : str = ""
    zip     : str = ""
    ip      : str = ""

    def first_name ( self ) -> str:

        return self.name.split(" ", 1)[0] if self.name else "NA"

    def last_name ( self ) -> str:

        parts = self.name.split(" ", 1)

        return parts[1] if len(parts) > 1 else "NA"

@dataclass(frozen=True, slots=True, kw_only=True)
class Payment:

    amount      : Money
    reference   : str
    description : str = ""
    customer    : Customer = field(default_factory=Customer)
    return_url  : str = ""
    cancel_url  : str = ""
    notify_url  : str = ""
    capture     : bool = True
    methods     : tuple[str, ...] = ()
    metadata    : dict[str, str] = field(default_factory=dict)
    key         : str | None = None

    def with_ ( self, **changes: Any ) -> Payment:

        return replace(self, **changes)

@dataclass(frozen=True, slots=True, kw_only=True)
class Payout:

    amount    : Money
    reference : str
    recipient : str
    channel   : str = "email"
    note      : str = ""
    metadata  : dict[str, str] = field(default_factory=dict)
    key       : str | None = None

@dataclass(frozen=True, slots=True, kw_only=True)
class Transaction:

    provider        : str
    id              : str
    kind            : Kind
    status          : Status
    amount          : Money
    reference       : str = ""
    total_amount    : Money | None = None
    gross_amount    : Money | None = None
    net_amount      : Money | None = None
    fee_amount      : Money | None = None
    captured_amount : Money | None = None
    refunded_amount : Money | None = None
    parent_id       : str | None = None
    method          : str | None = None
    card_brand      : str | None = None
    card_last4      : str | None = None
    customer_email  : str | None = None
    redirect_url    : str | None = None
    client_secret   : str | None = None
    error_code      : str | None = None
    error_message   : str | None = None
    created_at      : str | None = None
    test            : bool = False
    raw             : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def currency ( self ) -> str:

        return self.amount.currency

    def paid ( self ) -> bool:

        return self.status.settled()

    def dump ( self, raw: bool = False ) -> dict[str, Any]:

        money = (
            "amount", "total_amount", "gross_amount", "net_amount", "fee_amount", "captured_amount", "refunded_amount",
        )
        found = { name: getattr(self, name) for name in self.__dataclass_fields__ if raw or name != "raw" }

        for name in money:

            value = found.get(name)

            found[name] = value.dump() if isinstance(value, Money) else None

        found["kind"], found["status"], found["currency"] = self.kind.value, self.status.value, self.currency()

        return found

@dataclass(frozen=True, slots=True, kw_only=True)
class Notice:

    provider    : str
    id          : str
    type        : str
    transaction : Transaction | None = None
    raw         : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)
