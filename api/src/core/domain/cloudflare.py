from collections.abc import Mapping
from typing import Any, ClassVar, override

from core.error import Code
from core.net import Remote, Transport
from core.number import Money
from .contract import (
    BUY, CHECK, DELETE, EXISTS, GET, RECORDS, SET, UNSET, VERIFY, Availability, Contact, Domain, Record, Registrar,
    Registration, Verification, record_of,
)

BASE = "https://api.cloudflare.com/client/v4"
DONE = ("active", "succeeded")

class Cloudflare(Remote, Registrar):

    name         = "cloudflare"
    capabilities : ClassVar[frozenset[str]] = frozenset({CHECK, BUY, GET, EXISTS, DELETE, RECORDS, SET, UNSET, VERIFY})

    def __init__ (
        self, token: str, account: str, zone: str = "", base: str = "", wait: float = 20.0,
        transport: Transport | None = None,
    ) -> None:

        Remote.__init__(self, base or BASE, wait, 2, transport)

        self.missing(("token", token), ("account", account))

        self._token   = token
        self._account = account
        self._zone    = zone
        self._zones: dict[str, str] = {}

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._token}" }

    async def result ( self, method: str, path: str, action: str, body: object = None, **params: object ) -> Any:

        found = await self.call(method, path, action, json=body, params=params or None)

        return found.get("result") if isinstance(found, Mapping) else None

    async def zone_of ( self, name: str ) -> str:

        apex = ".".join(name.lower().rstrip(".").split(".")[-2:])

        if apex in self._zones: return self._zones[apex]

        found = await self.result("GET", "/zones", "zone", name=apex) or []

        if not found: raise self.fault(Code.NOT_FOUND, "zone")

        self._zones[apex] = str(found[0]["id"])

        return self._zones[apex]

    @override
    async def check ( self, *names: str ) -> list[Availability]:

        path  = f"/accounts/{self._account}/registrar/domain-check"
        found = await self.result("POST", path, "check", { "domains": list(names) })

        return [self.availability(item) for item in (found or {}).get("domains", [])]

    def availability ( self, item: Mapping[str, Any] ) -> Availability:

        pricing  = item.get("pricing") or {}
        currency = str(pricing.get("currency") or "USD")
        cost     = pricing.get("registration_cost")
        renew    = pricing.get("renewal_cost")

        return Availability(
            name=str(item.get("name", "")), available=bool(item.get("registrable")),
            premium=item.get("tier") == "premium",
            price=Money.of(cost, currency) if cost else None, renewal=Money.of(renew, currency) if renew else None,
            reason=item.get("reason"), raw=dict(item),
        )

    @override
    async def buy ( self, name: str, years: int = 1, contact: Contact | None = None ) -> Registration:

        body: dict[str, Any] = { "domain_name": name }

        if contact is not None:
            address = {
                "street": contact.street, "city": contact.city, "state": contact.state,
                "postal_code": contact.postal_code, "country_code": contact.country,
            }
            postal  = { "name": contact.name, "organization": contact.organization, "address": address }
            person  = { "email": contact.email, "phone": contact.phone, "postal_info": postal }

            body["contacts"] = { "registrant": person }

        found = await self.result("POST", f"/accounts/{self._account}/registrar/registrations", "buy", body) or {}
        inner = (found.get("context") or {}).get("registration") or {}

        return Registration(
            name=str(found.get("domain_name", name)), status=str(found.get("state", "in_progress")),
            completed=bool(found.get("completed")), expires_at=inner.get("expires_at"), raw=dict(found),
        )

    @override
    async def get ( self, name: str ) -> Domain:

        found = await self.result("GET", f"/accounts/{self._account}/registrar/domains/{name}", "get") or {}

        return Domain(
            name=str(found.get("name", name)), status=str(found.get("status") or "unknown"),
            nameservers=tuple(found.get("name_servers") or ()), expires_at=found.get("expires_at"),
            auto_renew=bool(found.get("auto_renew")), raw=dict(found),
        )

    @override
    async def exists ( self, name: str ) -> bool:

        apex = ".".join(name.lower().rstrip(".").split(".")[-2:])

        return bool(await self.result("GET", "/zones", "exists", name=apex))

    @override
    async def records ( self, zone: str ) -> list[Record]:

        found = await self.result("GET", f"/zones/{await self.zone_of(zone)}/dns_records", "records", per_page=500)

        return [record_of(item) for item in found or []]

    @override
    async def set ( self, zone: str, record: Record ) -> Record:

        known = { item.key(): item for item in await self.records(zone) }
        body  = {
            "type": record.type.upper(), "name": record.name, "content": record.value, "ttl": record.ttl,
            "proxied": record.proxied, "priority": record.priority,
        }
        base  = f"/zones/{await self.zone_of(zone)}/dns_records"
        same  = known.get(record.key())
        path  = f"{base}/{same.id}" if same else base
        found = await self.result("PATCH" if same else "POST", path, "set", body)

        return record_of(found or {})

    @override
    async def unset ( self, zone: str, key: str ) -> bool:

        await self.result("DELETE", f"/zones/{await self.zone_of(zone)}/dns_records/{key}", "unset")

        return True

    @override
    async def verify ( self, host: str ) -> Verification:

        zone  = await self.zone_of(self._zone or host)
        known = await self.result("GET", f"/zones/{zone}/custom_hostnames", "verify", hostname=host) or []
        body  = { "hostname": host, "ssl": { "method": "http", "type": "dv" } }
        found = known[0] if known else await self.result("POST", f"/zones/{zone}/custom_hostnames", "verify", body)

        return self.verification(host, found or {})

    def verification ( self, host: str, found: Mapping[str, Any] ) -> Verification:

        owner  = found.get("ownership_verification") or {}
        ssl    = found.get("ssl") or {}
        kind   = str(owner.get("type", "txt")).upper()
        proof  = Record(type=kind, name=str(owner.get("name", "")), value=str(owner.get("value", "")))
        needed = [proof] if owner else []
        checks = [
            Record(type="TXT", name=str(item.get("txt_name", "")), value=str(item.get("txt_value", "")))
            for item in ssl.get("validation_records") or [] if item.get("txt_name")
        ]
        status = str(found.get("status", "pending"))
        ready  = status in DONE and ssl.get("status") == "active"

        return Verification(host=host, verified=ready, status=status, records=(*needed, *checks), raw=dict(found))

    @override
    async def delete ( self, host: str ) -> bool:

        zone  = await self.zone_of(self._zone or host)
        known = await self.result("GET", f"/zones/{zone}/custom_hostnames", "delete", hostname=host) or []

        if not known: return False

        await self.result("DELETE", f"/zones/{zone}/custom_hostnames/{known[0]['id']}", "delete")

        return True
