from collections.abc import Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from engine.domain import Contact, Domains, Local
from engine.error import Code
from engine.json import json
from engine.net import Answer, Ask, net
from engine.number import Money
from engine.test import expect, test
import pytest

type Handler = Callable[[Ask], Answer]

def wire ( routes: Mapping[tuple[str, str], Handler], seen: list[Ask] ) -> Callable[[Ask], Answer]:

    def answer ( asked: Ask ) -> Answer:

        seen.append(asked)

        handler = routes.get((asked.method, urlsplit(asked.url).path))

        if handler is None: return 404, b'{"error": {"message": "missing"}}', { "content-type": "application/json" }

        return handler(asked)

    return answer

def reply ( payload: object, status: int = 200 ) -> Answer:

    return status, json.encode(payload), { "content-type": "application/json" }

@pytest.mark.anyio
class TestDomains:

    async def test_the_local_registrar_runs_the_whole_verification_loop ( self ) -> None:

        own = Domains()

        own.connect("local", taken=("taken.test",))

        offers = await own.check("free.test", "taken.test")

        expect([(offer.name, offer.available, offer.price) for offer in offers]).equals(
            [("free.test", True, Money.of(12, "USD")), ("taken.test", False, None)],
        )
        expect((await own.buy("free.test")).completed).true()
        expect((await own.available("free.test"), await own.exists("free.test"))).equals((False, True))

        with test.fails(Code.CONFLICT, "domain.local.buy.taken.test"): await own.buy("taken.test")

        first = await own.subdomain("free.test", "acme", "edge.brand.test")
        again = await own.subdomain("free.test", "acme", "edge2.brand.test")

        expect((first.id, again.value, len(await own.records("free.test")))).equals((again.id, "edge2.brand.test", 1))

        pending = await own.verify("chat.free.test")

        expect((pending.verified, pending.records[0].name)).equals((False, "_verify.chat.free.test"))

        await own.set("free.test", "txt", pending.records[0].name, pending.records[0].value)

        expect((await own.verify("chat.free.test")).verified).true()
        unset   = await own.unset("free.test", first.id)
        removed = (unset, await own.delete("chat.free.test"), await own.delete("x.test"))

        expect(removed).equals((True, True, False))

    async def test_cloudflare_and_vercel_speak_their_own_wires_behind_one_dsl ( self ) -> None:

        seen: list[Ask] = []
        zone = "023e105f4ecef8ad9ca31a8372d0c353"
        pricing  = { "currency": "USD", "registration_cost": "10.11", "renewal_cost": "10.11" }
        checked  = { "domains": [
            { "name": "brand.dev", "registrable": True, "tier": "standard", "pricing": pricing },
            { "name": "google.com", "registrable": False, "reason": "domain_unavailable" },
        ] }
        started  = { "domain_name": "brand.dev", "state": "in_progress", "completed": False }
        existing = { "id": "rec1", "type": "CNAME", "name": "acme.brand.dev", "content": "old.test", "ttl": 1 }
        owner    = { "type": "txt", "name": "_cf-custom-hostname.chat.acme.test", "value": "uuid" }
        checks   = [{ "txt_name": "_acme", "txt_value": "tok" }]
        ssl      = { "status": "pending_validation", "validation_records": checks }
        hostname = { "id": "ch1", "hostname": "chat.acme.test", "status": "pending", "ownership_verification": owner }
        offer    = { "domain": "brand.app", "available": "true", "years": 1, "price": 14, "renewalPrice": 16 }
        proof    = { "type": "TXT", "domain": "_vercel.acme.test", "value": "vc=1" }
        account  = "/client/v4/accounts/acc/registrar"
        records  = f"/client/v4/zones/{zone}/dns_records"
        hosts    = f"/client/v4/zones/{zone}/custom_hostnames"
        routes: dict[tuple[str, str], Handler] = {
            ("POST", f"{account}/domain-check"): lambda asked: reply({ "success": True, "result": checked }),
            ("POST", f"{account}/registrations"): lambda asked: reply({ "success": True, "result": started }, 202),
            ("GET", "/client/v4/zones"): lambda asked: reply({ "success": True, "result": [{ "id": zone }] }),
            ("GET", records): lambda asked: reply({ "success": True, "result": [existing] }),
            ("PATCH", f"{records}/rec1"): lambda asked: reply({ "result": { "id": "rec1", **json.loads(asked.body) } }),
            ("GET", hosts): lambda asked: reply({ "success": True, "result": [] }),
            ("POST", hosts): lambda asked: reply({ "success": True, "result": { **hostname, "ssl": ssl } }),
            ("POST", "/v1/registrar/domains/search"): lambda asked: reply({ "results": [offer] }),
            ("GET", "/v9/projects/web/domains/chat.acme.test"): lambda asked: reply({ "error": "no" }, 404),
            ("POST", "/v10/projects/web/domains"): lambda asked: reply({ "name": "chat.acme.test" }),
            ("POST", "/v9/projects/web/domains/chat.acme.test/verify"): lambda asked: reply(
                { "verified": False, "verification": [proof] },
            ),
        }
        own = Domains()
        tap = net.mocked(wire(routes, seen))

        own.connect("cloudflare", tap, token="cf-token", account="acc", zone="brand.dev")
        own.connect("vercel", tap, token="vc-token", project="web", team="team_1")

        offers = await own.check("brand.dev", "google.com")

        expect([(offer.available, offer.price, offer.reason) for offer in offers]).equals(
            [(True, Money.of("10.11", "USD"), None), (False, None, "domain_unavailable")],
        )
        expect(seen[-1].headers["authorization"]).equals("Bearer cf-token")
        expect((await own.buy("brand.dev")).status).equals("in_progress")

        record = await own.subdomain("brand.dev", "acme", "edge.brand.test", proxied=True)

        expect((record.id, record.value, seen[-1].method, json.loads(seen[-1].body)["content"])).equals(
            ("rec1", "edge.brand.test", "PATCH", "edge.brand.test"),
        )

        zones = [asked for asked in seen if urlsplit(asked.url).path == "/client/v4/zones"]

        expect(len(zones)).equals(1)

        claim = await own.verify("chat.acme.test")

        expect((claim.verified, [item.name for item in claim.records])).equals(
            (False, ["_cf-custom-hostname.chat.acme.test", "_acme"]),
        )

        found = await own.check("brand.app", using="vercel")

        expect((found[0].available, found[0].price, found[0].renewal)).equals(
            (True, Money.of(14, "USD"), Money.of(16, "USD")),
        )
        expect(parse_qs(urlsplit(seen[-1].url).query)).equals({ "teamId": ["team_1"] })

        pending = await own.verify("chat.acme.test", using="vercel")

        expect((pending.verified, pending.records[0].value, seen[-2].method)).equals((False, "vc=1", "POST"))

        with test.fails(Code.BAD_REQUEST, "domain.vercel.buy.contact"): await own.buy("brand.app", using="vercel")
        with test.fails(Code.INTERNAL, "domain.ghost.missing"): own.connect("ghost")

        expect(own.describe()["providers"]).equals(["cloudflare", "vercel"])
        expect(Contact(name="Ann Lee", email="a@x.test", phone="+20.1").name).equals("Ann Lee")
        expect(isinstance(own.use("cloudflare"), Local)).false()
