from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, ClassVar, override

from engine.adapter import Adapter
from engine.error import Code
from engine.number import Money
from engine.rand import rand

CHECK     = "check"
BUY       = "buy"
GET       = "get"
EXISTS    = "exists"
DELETE    = "delete"
RECORDS   = "records"
SET       = "set"
UNSET     = "unset"
VERIFY    = "verify"
EVERY     = frozenset({CHECK, BUY, GET, EXISTS, DELETE, RECORDS, SET, UNSET, VERIFY})
PRICE = Money.of("12.00", "USD")

@dataclass(frozen=True, slots=True, kw_only=True)
class Availability:

    name      : str
    available : bool
    price     : Money | None = None
    renewal   : Money | None = None
    premium   : bool = False
    reason    : str | None = None
    raw       : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Record:

    type     : str
    name     : str
    value    : str
    ttl      : int = 1
    proxied  : bool = False
    priority : int | None = None
    id       : str = ""
    raw      : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def key ( self ) -> tuple[str, str]:

        return self.type.upper(), self.name.lower().rstrip(".")

    def dump ( self ) -> dict[str, Any]:

        return {
            "id": self.id, "type": self.type, "name": self.name, "value": self.value, "ttl": self.ttl,
            "proxied": self.proxied, "priority": self.priority,
        }

@dataclass(frozen=True, slots=True, kw_only=True)
class Registration:

    name       : str
    status     : str
    completed  : bool = False
    expires_at : str | None = None
    raw        : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Domain:

    name        : str
    status      : str
    nameservers : tuple[str, ...] = ()
    expires_at  : str | None = None
    auto_renew  : bool = False
    raw         : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Verification:

    host     : str
    verified : bool
    status   : str
    records  : tuple[Record, ...] = ()
    raw      : dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

@dataclass(frozen=True, slots=True, kw_only=True)
class Contact:

    name         : str
    email        : str
    phone        : str
    street       : str = ""
    city         : str = ""
    state        : str = ""
    postal_code  : str = ""
    country      : str = ""
    organization : str = ""

class Registrar(Adapter, ABC):

    family : ClassVar[str] = "domain"

    async def check ( self, *names: str ) -> list[Availability]:

        raise self.unsupported(CHECK)

    async def buy ( self, name: str, years: int = 1, contact: Contact | None = None ) -> Registration:

        raise self.unsupported(BUY)

    async def get ( self, name: str ) -> Domain:

        raise self.unsupported(GET)

    async def exists ( self, name: str ) -> bool:

        raise self.unsupported(EXISTS)

    async def delete ( self, host: str ) -> bool:

        raise self.unsupported(DELETE)

    async def records ( self, zone: str ) -> list[Record]:

        raise self.unsupported(RECORDS)

    async def set ( self, zone: str, record: Record ) -> Record:

        raise self.unsupported(SET)

    async def unset ( self, zone: str, key: str ) -> bool:

        raise self.unsupported(UNSET)

    async def verify ( self, host: str ) -> Verification:

        raise self.unsupported(VERIFY)

def record_of ( found: Mapping[str, Any], value: str = "content" ) -> Record:

    return Record(
        id=str(found.get("id") or found.get("uid") or ""), type=str(found.get("type", "")),
        name=str(found.get("name", "")), value=str(found.get(value) or found.get("value") or ""),
        ttl=int(found.get("ttl") or 1), proxied=bool(found.get("proxied", False)), priority=found.get("priority"),
        raw=dict(found),
    )

class Local(Registrar):

    name         = "local"
    capabilities : ClassVar[frozenset[str]] = EVERY

    def __init__ ( self, taken: tuple[str, ...] = () ) -> None:

        self._taken = { name.lower() for name in taken }
        self._owned: set[str] = set()
        self._zones: dict[str, dict[str, Record]] = {}
        self._hosts: dict[str, str] = {}

    @override
    async def check ( self, *names: str ) -> list[Availability]:

        held = self._taken | self._owned

        return [
            Availability(name=name, available=name.lower() not in held, price=None if name.lower() in held else PRICE)
            for name in names
        ]

    @override
    async def buy ( self, name: str, years: int = 1, contact: Contact | None = None ) -> Registration:

        found = (await self.check(name))[0]

        if not found.available: raise self.fault(Code.CONFLICT, f"buy.{name}")

        self._owned.add(name.lower())
        self._zones.setdefault(name.lower(), {})

        return Registration(name=name, status="succeeded", completed=True)

    @override
    async def get ( self, name: str ) -> Domain:

        status = "active" if name.lower() in self._owned else "unknown"

        return Domain(name=name, status=status, nameservers=("ns1.local", "ns2.local"))

    @override
    async def exists ( self, name: str ) -> bool:

        return name.lower() in self._owned or name.lower() in self._hosts

    @override
    async def delete ( self, host: str ) -> bool:

        return self._hosts.pop(host.lower(), None) is not None

    @override
    async def records ( self, zone: str ) -> list[Record]:

        return list(self._zones.get(zone.lower(), {}).values())

    @override
    async def set ( self, zone: str, record: Record ) -> Record:

        kept  = self._zones.setdefault(zone.lower(), {})
        same  = next((item for item in kept.values() if item.key() == record.key()), None)
        saved = replace(record, id=same.id if same else rand.hex(6))

        kept[saved.id] = saved

        return saved

    @override
    async def unset ( self, zone: str, key: str ) -> bool:

        return self._zones.get(zone.lower(), {}).pop(key, None) is not None

    @override
    async def verify ( self, host: str ) -> Verification:

        token = self._hosts.setdefault(host.lower(), rand.hex(12))
        proof = Record(type="TXT", name=f"_verify.{host}", value=token)
        zone  = ".".join(host.lower().split(".")[-2:])
        done  = any(item.key() == proof.key() and item.value == token for item in await self.records(zone))

        status = "verified" if done else "pending"

        return Verification(host=host, verified=done, status=status, records=() if done else (proof,))
