from collections.abc import Mapping
from typing import Any, ClassVar, override

from core.error import Code, Fault
from core.net import Remote, Transport
from core.number import Money
from .contract import (
    BUY, CHECK, DELETE, EXISTS, GET, RECORDS, SET, UNSET, VERIFY, Availability, Contact, Domain, Record, Registrar,
    Registration, Verification, record_of,
)

BASE = "https://api.vercel.com"

def proof ( item: Mapping[str, Any] ) -> Record:

    kind = str(item.get("type", "TXT")).upper()

    return Record(type=kind, name=str(item.get("domain", "")), value=str(item.get("value")))

class Vercel(Remote, Registrar):

    name         = "vercel"
    capabilities : ClassVar[frozenset[str]] = frozenset({CHECK, BUY, GET, EXISTS, DELETE, RECORDS, SET, UNSET, VERIFY})

    def __init__ (
        self, token: str, project: str = "", team: str = "", base: str = "", wait: float = 20.0,
        transport: Transport | None = None,
    ) -> None:

        Remote.__init__(self, base or BASE, wait, 2, transport)

        self.missing(("token", token))

        self._token   = token
        self._project = project
        self._team    = team

    @override
    def headers ( self ) -> dict[str, str]:

        return { "authorization": f"Bearer {self._token}" }

    def scope ( self ) -> dict[str, object] | None:

        return { "teamId": self._team } if self._team else None

    async def ask ( self, method: str, path: str, action: str, body: object = None ) -> Any:

        return await self.call(method, path, action, json=body, params=self.scope())

    def project ( self ) -> str:

        if not self._project: raise self.fault(Code.INTERNAL, "config.project")

        return self._project

    @override
    async def check ( self, *names: str ) -> list[Availability]:

        found = await self.ask("POST", "/v1/registrar/domains/search", "check", { "domains": list(names) })

        return [self.availability(item) for item in found.get("results", [])]

    def availability ( self, item: Mapping[str, Any] ) -> Availability:

        price = item.get("price")
        renew = item.get("renewalPrice")
        free  = str(item.get("available")).lower() == "true"

        return Availability(
            name=str(item.get("domain", "")), available=free, premium=bool(item.get("premium")),
            price=Money.of(price, "USD") if price is not None else None,
            renewal=Money.of(renew, "USD") if renew is not None else None, raw=dict(item),
        )

    @override
    async def buy ( self, name: str, years: int = 1, contact: Contact | None = None ) -> Registration:

        if contact is None: raise Fault(Code.BAD_REQUEST, reason="domain.vercel.buy.contact")

        offer  = (await self.check(name))[0]
        person = {
            "firstName": contact.name.split(" ", 1)[0], "lastName": contact.name.split(" ", 1)[-1],
            "email": contact.email, "phone": contact.phone, "address1": contact.street, "city": contact.city,
            "state": contact.state, "zip": contact.postal_code, "country": contact.country,
        }

        if contact.organization: person["companyName"] = contact.organization

        if not offer.available or offer.price is None: raise self.fault(Code.CONFLICT, "buy.unavailable")

        body  = {
            "autoRenew": True, "years": years, "expectedPrice": float(offer.price.amount), "contactInformation": person,
        }
        found = await self.ask("POST", f"/v1/registrar/domains/{name}/buy", "buy", body)

        return Registration(name=name, status=str(found.get("status", "pending")), raw=dict(found))

    @override
    async def get ( self, name: str ) -> Domain:

        found = (await self.ask("GET", f"/v5/domains/{name}", "get")).get("domain") or {}

        return Domain(
            name=str(found.get("name", name)), status="verified" if found.get("verified") else "pending",
            nameservers=tuple(found.get("nameservers") or ()), expires_at=str(found.get("expiresAt") or "") or None,
            auto_renew=bool(found.get("renew")), raw=dict(found),
        )

    @override
    async def exists ( self, name: str ) -> bool:

        try: await self.ask("GET", f"/v9/projects/{self.project()}/domains/{name}", "exists")
        except Fault as fault:

            if fault.code is Code.NOT_FOUND: return False

            raise

        return True

    @override
    async def records ( self, zone: str ) -> list[Record]:

        found = await self.ask("GET", f"/v5/domains/{zone}/records", "records")

        return [record_of(item, "value") for item in found.get("records", [])]

    @override
    async def set ( self, zone: str, record: Record ) -> Record:

        label = record.name.removesuffix(f".{zone}") if record.name != zone else ""
        known = { item.key(): item for item in await self.records(zone) }
        same  = known.get((record.type.upper(), label))
        body  = { "name": label, "type": record.type.upper(), "value": record.value, "ttl": max(record.ttl, 60) }

        if same: await self.ask("DELETE", f"/v2/domains/{zone}/records/{same.id}", "set")

        found = await self.ask("POST", f"/v2/domains/{zone}/records", "set", body)

        made  = str(found.get("uid", ""))

        return Record(type=record.type.upper(), name=label, value=record.value, ttl=max(record.ttl, 60), id=made)

    @override
    async def unset ( self, zone: str, key: str ) -> bool:

        await self.ask("DELETE", f"/v2/domains/{zone}/records/{key}", "unset")

        return True

    @override
    async def verify ( self, host: str ) -> Verification:

        project = self.project()

        if not await self.exists(host):
            await self.ask("POST", f"/v10/projects/{project}/domains", "verify", { "name": host })

        try: found = await self.ask("POST", f"/v9/projects/{project}/domains/{host}/verify", "verify")
        except Fault as fault:

            if fault.code is not Code.BAD_REQUEST: raise

            found = await self.ask("GET", f"/v9/projects/{project}/domains/{host}", "verify")

        needed = tuple(proof(item) for item in found.get("verification") or [])
        ready  = bool(found.get("verified"))
        status = "verified" if ready else "pending"

        return Verification(host=host, verified=ready, status=status, records=needed, raw=dict(found))

    @override
    async def delete ( self, host: str ) -> bool:

        if not await self.exists(host): return False

        await self.ask("DELETE", f"/v9/projects/{self.project()}/domains/{host}", "delete")

        return True
