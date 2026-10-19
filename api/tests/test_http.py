from collections.abc import AsyncIterator, Mapping
from typing import ClassVar

from core.error import Code, Fault, Faults
from core.exception import Handler, Target, exception
from core.http import Request, Response, Route, Sse, Upload, http
from core.test import Client, expect, test
from core.validate import Shape, field
import pytest

faults = Faults()

class Mapped(Handler):

    maps : ClassVar[Mapping[type[BaseException], Target]] = { ValueError: Code.BAD_REQUEST }

class Search(Shape):

    term  : str = field(min_length=2)
    limit : int = field(10, ge=1, le=50)

class ItemsController:

    async def index ( self ) -> Response:

        return Response.page([{ "id": 1 }], 41, 2, 20)

    async def show ( self, key: int ) -> Response:

        return Response.ok({ "id": key })

    async def store ( self ) -> Response:

        return Response.created({ "id": 2 })

    async def destroy ( self, key: int ) -> Response:

        return Response.ok(message=f"removed {key}")

    async def crash ( self ) -> Response:

        raise RuntimeError("secret detail")

    async def mistake ( self ) -> Response:

        raise ValueError("bad input")

    async def refuse ( self ) -> Response:

        raise faults.forbidden("not yours")

    async def whoami ( self, request: Request ) -> Response:

        return Response.ok({ "user": request.user() })

async def gate ( request: Request ) -> None:

    if request.header("x-key") != "open": raise Fault(Code.UNAUTHORIZED, reason="key")

    request.assign(user="keyholder")

async def tenant ( request: Request ) -> None:

    request.assign(tenant=request.header("x-tenant"))

    if not request.state("tenant"): raise Fault(Code.BAD_REQUEST, reason="tenant")

async def member ( request: Request ) -> None:

    if request.state("tenant") != "acme": raise Fault(Code.FORBIDDEN, reason="tenant.member")

items  = ItemsController()
groups = [
    Route.group("/v1", [
        Route.resource("/items", items, only=("index", "show", "store", "destroy")),
        Route.get("/items/{key}/typed", items.show, name="typed").constrained(key="int"),
        Route.get("/crash", items.crash, name="crash"),
        Route.get("/mistake", items.mistake, name="mistake"),
        Route.get("/refuse", items.refuse, name="refuse"),
        Route.group("/private", [Route.get("/me", items.whoami, name="me")], middleware=(gate,), name="private"),
        Route.get("/limited", items.index, name="limited").limited("2/minute"),
        Route.get("/also-limited", items.index, name="also").limited("2/minute"),
        Route.group("/tenants", [
            Route.group("/acme", [
                Route.get("/orders", items.index, name="orders"),
                Route.get("/slow", items.index, name="slow").limited("1/minute"),
            ], middleware=(member,), name="acme"),
        ], middleware=(tenant,), throttle="3/minute", name="tenants"),
    ], name="v1", tags=("v1",)),
]

def forwarded ( address: str ) -> dict[str, str]:

    return { "X-Forwarded-For": address }

@pytest.fixture
async def bare () -> AsyncIterator[Client]:

    exception.use(Mapped())

    app = http.build("Bare", "0.0.1", groups, origins=["http://web.test"])

    async with test.client(app, "http://bare") as client: yield client

@pytest.mark.anyio
class TestHttp:

    async def test_route_dsl_composes_names_prefixes_resources_and_constraints ( self, bare: Client ) -> None:

        walked = { bound.name: bound for bound in groups[0].walk() }

        expect(groups[0].names()).equals([
            "v1.items.index", "v1.items.store", "v1.items.show", "v1.items.destroy", "v1.typed",
            "v1.crash", "v1.mistake", "v1.refuse", "v1.private.me", "v1.limited", "v1.also",
            "v1.tenants.acme.orders", "v1.tenants.acme.slow",
        ])
        expect((walked["v1.typed"].path, walked["v1.private.me"].middleware)).equals(
            ("/v1/items/{key:int}/typed", (gate,)),
        )
        expect(groups[0].walk()).each(lambda bound: bound.tags == ("v1",))
        expect((walked["v1.tenants.acme.orders"].path, walked["v1.tenants.acme.orders"].throttle)).equals(
            ("/v1/tenants/acme/orders", "3/minute"),
        )
        expect((walked["v1.tenants.acme.slow"].middleware, walked["v1.tenants.acme.slow"].throttle)).equals(
            ((tenant, member), "1/minute"),
        )

        with test.fails(Code.INTERNAL, "http.converter.key:regex"):
            Route.get("/x", items.index).constrained(key="regex")

        listed = (await bare.get("/v1/items")).ok().header("x-content-type-options", "nosniff")

        expect(listed.json()).subset({
            "data": [{ "id": 1 }], "meta": {
                "request_id": listed.headers["x-request-id"], "page": 2, "limit": 20, "total": 41, "pages": 3,
            },
        })
        expect((await bare.get("/v1/items/7")).ok().data()).equals({ "id": 7 })
        (await bare.post("/v1/items")).created().expect("code").equals("created")
        (await bare.delete("/v1/items/7")).ok().expect("message").equals("removed 7")

        (await bare.get("/v1/items/x/typed")).fault(Code.NOT_FOUND)
        (await bare.put("/v1/items")).fault(Code.METHOD_NOT_ALLOWED)
        (await bare.get("/v1/nowhere")).fault(Code.NOT_FOUND).expect("data").none()
        (await bare.get("/openapi.json")).status(404)
        (await bare.get("/docs")).status(404)

    async def test_failures_are_enveloped_masked_and_traced ( self, bare: Client ) -> None:

        crashed = await bare.get("/v1/crash", headers={ "X-Request-Id": "trace-123" })
        mapped  = await bare.get("/v1/mistake")
        bogus   = await bare.get("/v1/items", headers={ "X-Request-Id": "bad id with spaces" })

        crashed.fault(Code.INTERNAL).header("x-request-id", "trace-123").expect("meta.request_id").equals("trace-123")
        mapped.fault(Code.BAD_REQUEST)

        expect(crashed.text()).lacks("secret")
        expect(mapped.text()).lacks("bad input")
        expect(bogus.headers["x-request-id"]).differs("bad id with spaces").length(36)

        (await bare.get("/v1/refuse")).fault(Code.FORBIDDEN, "not yours")
        (await bare.get("/v1/private/me")).fault(Code.UNAUTHORIZED, "key")

        expect((await bare.get("/v1/private/me", headers={ "x-key": "open" })).data()).equals({ "user": "keyholder" })

    async def test_throttle_counts_per_scope_and_per_client_and_ignores_spoofed_hops ( self, bare: Client ) -> None:

        burst = [await bare.get("/v1/limited", headers=forwarded("10.1.0.1")) for _ in range(3)]
        other = await bare.get("/v1/also-limited", headers=forwarded("10.1.0.1"))
        fresh = await bare.get("/v1/limited", headers=forwarded("10.1.0.2"))

        expect([reply.code for reply in burst]).equals([200, 200, 429])
        expect([reply.headers["x-ratelimit-remaining"] for reply in burst]).equals(["1", "0", "0"])
        expect(burst).each(lambda reply: reply.headers["x-ratelimit-limit"] == "2")
        expect(float(burst[2].headers["x-ratelimit-reset"])).between(0, 60)
        expect(int(burst[2].fault(Code.TOO_MANY_REQUESTS, "throttle").headers["retry-after"])).between(1, 60)
        expect((other.code, fresh.code)).equals((200, 200))

        inside   = { **forwarded("10.1.0.9"), "X-Tenant": "acme" }
        nobody   = await bare.get("/v1/tenants/acme/orders", headers=forwarded("10.1.0.9"))
        stranger = await bare.get("/v1/tenants/acme/orders", headers={ **forwarded("10.1.0.9"), "X-Tenant": "other" })
        allowed  = [await bare.get("/v1/tenants/acme/orders", headers=inside) for _ in range(4)]
        narrow   = [await bare.get("/v1/tenants/acme/slow", headers=inside) for _ in range(2)]

        nobody.fault(Code.BAD_REQUEST, "tenant").lacks("x-ratelimit-limit")
        stranger.fault(Code.FORBIDDEN, "tenant.member")

        expect([reply.code for reply in allowed]).equals([200, 200, 200, 429])
        expect([reply.code for reply in narrow]).equals([200, 429])
        expect((allowed[3].headers["x-ratelimit-limit"], narrow[1].headers["x-ratelimit-limit"])).equals(("3", "1"))

        app = http.build("Edge", "0.0.1", groups)

        async with test.client(app, "http://edge", peer=("203.0.113.9", 4000)) as outside:

            spoofed = [await outside.get("/v1/limited", headers=forwarded(f"10.9.0.{hop}")) for hop in range(3)]

        expect([reply.code for reply in spoofed]).equals([200, 200, 429])

    async def test_cors_opens_only_to_listed_origins ( self, bare: Client ) -> None:

        headers = { "Access-Control-Request-Method": "GET" }
        allowed = await bare.options("/v1/items", headers={ **headers, "Origin": "http://web.test" })
        denied  = await bare.options("/v1/items", headers={ **headers, "Origin": "http://evil.test" })
        simple  = await bare.get("/v1/items", headers={ "Origin": "http://web.test" })

        allowed.ok().header("access-control-allow-origin", "http://web.test")
        denied.status(400).lacks("access-control-allow-origin")
        simple.header("access-control-allow-origin", "http://web.test")

        expect(simple.headers["access-control-expose-headers"].lower()).contains("x-request-id", "retry-after")

async def echo ( request: Request ) -> Response:

    return Response.ok({
        "all": request.all(), "name": request.text("name"), "n": request.integer("n"), "flag": request.boolean("flag"),
        "tags": request.items("tags"), "has": request.has("name", "n"), "filled": request.filled("empty"),
        "bearer": request.bearer(), "json": request.is_json(), "route": request.route_name(), "ip": request.ip(),
        "only": request.only("name"), "nested": request.input("meta.deep"), "missing": request.missing("zzz"),
        "without": sorted(request.except_("name", "key", "n", "tags")), "wants": request.wants_json(),
    })

async def ticks () -> Response:

    async def source () -> AsyncIterator[Sse | dict[str, object] | str]:

        yield Sse({ "n": 1 }, event="tick", id="1")
        yield { "data": "two", "event": "tick" }
        yield "three"

    return Response.sse(source(), ping=0)

async def rows () -> Response:

    return Response.ndjson([{ "a": 1 }, { "b": 2 }])

async def gone () -> Response:

    return Response.redirect("/v2/items", 308)

async def shaped ( request: Request ) -> Response:

    return Response.ok(request.shape(name=str, age=int))

async def searched ( search: Search ) -> Response:

    return Response.ok(search.dump())

async def required ( request: Request ) -> Response:

    return Response.ok(request.require("name"))

async def lost ( request: Request ) -> Response:

    return Response.problem(Code.NOT_FOUND, request.param("fallback"))

async def received ( file: Upload, request: Request ) -> Response:

    return Response.created({ **file.describe(), "text": (await file.read()).decode(), "note": request.text("note") })

async def probe ( request: Request ) -> Response:

    day = request.date("day")

    return Response.ok({
        "agent": request.user_agent(), "ips": request.ips(), "is": request.is_("d/probe*"),
        "route": request.route_is("d.pr*"), "day": day.isoformat() if day else None,
        "merged": request.merge(x=1).input("x"), "has": request.when_has("name", str.upper, "none"),
        "filled": request.when_filled("empty", str.upper, "blank"), "file": request.has_file("upload"),
    }).cookie("seen", "1", max_age=60).header("x-custom", "1")

async def pulled () -> Response:

    async def chunks () -> AsyncIterator[bytes]:

        yield b"abc"

    return Response.stream(chunks(), name="dump.bin", download=True)

async def tenant_home ( request: Request ) -> Response:

    return Response.ok(request.state("domain"))

hosts = Route.group("/h", [
    Route.get("/home", tenant_home, name="home").domain("{tenant}.api.test"),
    Route.group("/t", [Route.get("/x", items.index, name="x")], name="t", domain="www.api.test"),
    Route.fallback(lost),
], name="h")

dsl = Route.group("/d", [
    Route.post("/echo/{key}", echo, name="echo"),
    Route.get("/events", ticks, name="events"),
    Route.get("/rows", rows, name="rows"),
    Route.get("/gone", gone, name="gone"),
    Route.post("/shaped", shaped, name="shaped"),
    Route.get("/search", searched, name="search"),
    Route.post("/search", searched, name="search.body"),
    Route.post("/required", required, name="required"),
    Route.post("/upload", received, name="upload"),
    Route.redirect("/old", "/d/rows", name="old"),
    Route.permanent_redirect("/older", "/d/rows", name="older"),
    Route.post("/probe", probe, name="probe"),
    Route.get("/pulled", pulled, name="pulled"),
], name="d")

@pytest.mark.anyio
class TestDsl:

    async def test_router_names_urls_and_one_response_type ( self ) -> None:

        app    = http.build("Dsl", "0.0.1", [dsl])
        router = app.router()
        things = Route.resource("/things", items, except_=("destroy",))

        expect((router.url("d.echo", key=7, page=2), http.url("d.rows"))).equals(("/d/echo/7?page=2", "/d/rows"))
        expect((router.params("d.echo"), router.has("d.gone"), http.has("nowhere"))).equals((["key"], True, False))
        expect((router.methods("/d/rows"), len(router.by_prefix("/d")), router.names()[0])).equals(
            (["GET"], 13, "d.echo"),
        )
        expect((router.describe()[0]["name"], router.find("d.old").methods)).equals(("d.echo", ("GET",)))
        expect(things.names()).equals(["things.index", "things.store", "things.show"])
        expect((Route.get("/x", items.index).tagged("a", "b").tags, Route.get("/x", items.index).hide().hidden)).equals(
            (("a", "b"), True),
        )
        expect(dsl.paths()).contains("/d/rows")
        expect([
            Response.problem(Code.CONFLICT, "dup").status(), Response.no_content().status(),
            Response.json({ "a": 1 }, 202).status(), Response.redirect("/x").status(),
        ]).equals([409, 204, 202, 307])
        expect((Response.text("hi").media_type, Response.raw(b"x").media_type, Response.no_content().body)).equals(
            ("text/plain", "application/octet-stream", b""),
        )
        expect(Response.ok().header("x-custom", "1").headers["x-custom"]).equals("1")
        expect(Response.fail(Fault(Code.TOO_MANY_REQUESTS, retry_after=2.2)).headers["retry-after"]).equals("3")

        with test.fails(Code.INTERNAL, "route.d.echo.key"): router.url("d.echo")
        with test.fails(Code.NOT_FOUND, "route.nowhere"): router.url("nowhere")

    async def test_request_verbs_shapes_uploads_and_streaming_replies ( self ) -> None:

        async with test.client(http.build("Dsl", "0.0.1", [dsl]), "http://dsl") as client:

            sent = await client.post(
                "/d/echo/9", params={ "n": "5", "tags[]": ["a", "b"] },
                json={ "name": " Ann ", "flag": "yes", "empty": "", "meta": { "deep": 1 } },
                headers={ "Authorization": "Bearer tok", "X-Forwarded-For": "10.0.0.7" },
            )

            expect(sent.ok().data()).subset({
                "name": "Ann", "n": 5, "flag": True, "tags": ["a", "b"], "has": True, "filled": False,
                "bearer": "tok", "json": True, "wants": True, "route": "d.echo", "ip": "10.0.0.7",
                "only": { "name": " Ann " }, "nested": 1, "all": { "key": "9" }, "missing": True,
                "without": ["empty", "flag", "meta"],
            })
            expect((await client.post("/d/shaped", data={ "name": "Bo", "age": "3" })).data()).equals(
                { "name": "Bo", "age": 3 },
            )
            expect((await client.get("/d/search", params={ "term": "ab" })).data()).equals(
                { "term": "ab", "limit": 10 },
            )
            expect((await client.post("/d/search", json={ "term": "abc", "limit": 3 })).data()).equals(
                { "term": "abc", "limit": 3 },
            )

            (await client.get("/d/search", params={ "term": "a", "limit": 99 })).fault(Code.VALIDATION, field="term")
            (await client.post("/d/search", json={ "term": "abc", "rogue": 1 })).fault(Code.VALIDATION, field="rogue")
            (await client.post("/d/echo/1", content=b"{bad", headers={ "content-type": "application/json" })).fault(
                Code.BAD_REQUEST, "json",
            )
            (await client.post("/d/required", json={})).fault(Code.VALIDATION, field="name")
            (await client.post("/d/shaped", json={ "name": "Bo", "age": "x" })).fault(Code.VALIDATION, field="age")
            (await client.post("/d/upload", data={ "note": "n" })).fault(Code.VALIDATION, field="file")

            attached = { "file": ("a.txt", b"hello", "text/plain") }
            upload   = await client.post("/d/upload", files=attached, data={ "note": "x" })
            events = (await client.get("/d/events")).ok().header("cache-control", "no-cache")
            lines  = (await client.get("/d/rows")).ok().header("content-type", "application/x-ndjson")

            expect(upload.created().data()).equals(
                { "name": "a.txt", "mime": "text/plain", "size": 5, "text": "hello", "note": "x" },
            )
            expect(events.headers["content-type"]).starts_with("text/event-stream")
            expect(events.text()).equals(
                'event: tick\nid: 1\ndata: {"n":1}\n\nevent: tick\ndata: two\n\ndata: three\n\n',
            )
            expect(lines.text()).equals('{"a":1}\n{"b":2}\n')

            (await client.get("/d/gone")).status(308).header("location", "/v2/items")
            (await client.get("/d/old")).status(307).header("location", "/d/rows")
            (await client.get("/d/older")).status(308).header("location", "/d/rows")

            probed = await client.post(
                "/d/probe", params={ "day": "2026-01-02", "name": "ann", "empty": "" },
                headers={ "User-Agent": "unit/1", "X-Forwarded-For": "10.0.0.1, 10.0.0.2" },
            )
            pulled = (await client.get("/d/pulled")).ok()

            pulled.header("content-disposition", 'attachment; filename="dump.bin"')

            expect(probed.header("x-custom", "1").data()).subset({
                "agent": "unit/1", "is": True, "route": True, "merged": 1, "has": "ANN", "filled": "blank",
                "file": False,
            })
            expect(probed.data("ips")).at("0").equals("10.0.0.1")
            expect(probed.data("day")).starts_with("2026-01-02")
            expect((probed.cookie("seen"), pulled.content)).equals(("1", b"abc"))

    async def test_domains_and_fallbacks_route_by_host ( self ) -> None:

        hosted = http.build("Hosts", "0.0.1", [hosts])

        expect(hosted.router().names()).equals(["h.home", "h.t.x", "h.fallback"])

        async with test.client(hosted, "http://acme.api.test") as client:

            expect((await client.get("/h/home")).data()).equals({ "tenant": "acme" })

            (await client.get("/h/anything/here")).fault(Code.NOT_FOUND, "anything/here")
            (await client.get("/h/t/x")).fault(Code.NOT_FOUND, "domain")

        async with test.client(hosted, "http://www.api.test") as client:

            (await client.get("/h/t/x")).ok()

            expect((await client.get("/h/home")).data()).equals({ "tenant": "www" })

        async with test.client(hosted, "http://nope.test") as client:

            (await client.get("/h/home")).fault(Code.NOT_FOUND, "domain")
