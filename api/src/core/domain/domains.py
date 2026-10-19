from typing import Any

from core.adapter import Manager
from core.error import Code, Fault
from core.log import log
from core.net import Transport
from .cloudflare import Cloudflare
from .contract import (
    BUY, CHECK, DELETE, EXISTS, GET, RECORDS, SET, UNSET, VERIFY, Availability, Contact, Domain, Local, Record,
    Registrar, Registration, Verification,
)
from .vercel import Vercel

class Domains(Manager[Registrar]):

    def __init__ ( self ) -> None:

        super().__init__("domain")

    def connect (
        self, name: str, transport: Transport | None = None, default: bool = False, **settings: Any,
    ) -> Registrar:

        token = str(settings.get("token", ""))
        made: Registrar

        match name:
            case "cloudflare":
                made = Cloudflare(token, settings.get("account", ""), settings.get("zone", ""), transport=transport)
            case "vercel":
                made = Vercel(token, settings.get("project", ""), settings.get("team", ""), transport=transport)
            case "local": made = Local(tuple(settings.get("taken", ())))
            case _: raise Fault(Code.INTERNAL, reason=f"domain.{name}.missing")

        return self.register(made, default)

    def chosen ( self, capability: str, using: str | None ) -> Registrar:

        adapter = self.use(using)

        adapter.require(capability)

        return adapter

    async def check ( self, *names: str, using: str | None = None ) -> list[Availability]:

        return await self.chosen(CHECK, using).check(*names)

    async def available ( self, name: str, using: str | None = None ) -> bool:

        found = await self.check(name, using=using)

        return bool(found) and found[0].available

    async def buy (
        self, name: str, years: int = 1, contact: Contact | None = None, using: str | None = None,
    ) -> Registration:

        made = await self.chosen(BUY, using).buy(name, years, contact)

        log.info("domain.bought", name=name, status=made.status, provider=self.use(using).name)

        return made

    async def get ( self, name: str, using: str | None = None ) -> Domain:

        return await self.chosen(GET, using).get(name)

    async def exists ( self, name: str, using: str | None = None ) -> bool:

        return await self.chosen(EXISTS, using).exists(name)

    async def delete ( self, host: str, using: str | None = None ) -> bool:

        return await self.chosen(DELETE, using).delete(host)

    async def records ( self, zone: str, using: str | None = None ) -> list[Record]:

        return await self.chosen(RECORDS, using).records(zone)

    async def set (
        self, zone: str, kind: str, name: str, value: str, ttl: int = 1, proxied: bool = False,
        using: str | None = None,
    ) -> Record:

        record = Record(type=kind.upper(), name=name, value=value, ttl=ttl, proxied=proxied)

        return await self.chosen(SET, using).set(zone, record)

    async def unset ( self, zone: str, key: str, using: str | None = None ) -> bool:

        return await self.chosen(UNSET, using).unset(zone, key)

    async def subdomain (
        self, zone: str, label: str, target: str, kind: str = "CNAME", proxied: bool = False, using: str | None = None,
    ) -> Record:

        return await self.set(zone, kind, f"{label}.{zone}", target, proxied=proxied, using=using)

    async def verify ( self, host: str, using: str | None = None ) -> Verification:

        found = await self.chosen(VERIFY, using).verify(host)

        log.info("domain.verified", host=host, verified=found.verified, status=found.status)

        return found
