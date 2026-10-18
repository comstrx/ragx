from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from core.error import Code, Fault, Faults
from core.exception import exception
from core.http import App, EventStream, Incoming, Redirect, Request, Response, Route, Sse, Streamed, http
from app.exceptions import ExceptionHandler
import pytest

faults = Faults()

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
        return Response.ok({ "user": request.state.user })

async def gate ( request: Request ) -> None:

    if request.headers.get("x-key") != "open": raise Fault(Code.UNAUTHORIZED, reason="key")

    request.state.user = "keyholder"

async def tenant ( request: Request ) -> None:

    request.state.tenant = request.headers.get("x-tenant", "")

    if not request.state.tenant: raise Fault(Code.BAD_REQUEST, reason="tenant")

async def member ( request: Request ) -> None:

    if request.state.tenant != "acme": raise Fault(Code.FORBIDDEN, reason="tenant.member")

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
async def bare () -> AsyncIterator[AsyncClient]:

    exception.use(ExceptionHandler())

    app       = http.build("Bare", "0.0.1", groups, origins=["http://web.test"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://bare") as client: yield client

@pytest.mark.anyio
class TestHttp:

    async def test_route_dsl_composes_names_prefixes_resources_and_constraints ( self, bare: AsyncClient ) -> None:

        assert groups[0].names() == [
            "v1.items.index", "v1.items.store", "v1.items.show", "v1.items.destroy", "v1.typed",
            "v1.crash", "v1.mistake", "v1.refuse", "v1.private.me", "v1.limited", "v1.also",
            "v1.tenants.acme.orders", "v1.tenants.acme.slow",
        ]
        assert next(bound for bound in groups[0].walk() if bound.name == "v1.typed").path == "/v1/items/{key:int}/typed"
        assert next(bound for bound in groups[0].walk() if bound.name == "v1.private.me").middleware == (gate,)
        assert all(bound.tags == ("v1",) for bound in groups[0].walk())

        orders = next(bound for bound in groups[0].walk() if bound.name == "v1.tenants.acme.orders")
        slow   = next(bound for bound in groups[0].walk() if bound.name == "v1.tenants.acme.slow")

        assert orders.path == "/v1/tenants/acme/orders"
        assert (orders.middleware, orders.throttle) == ((tenant, member), "3/minute")
        assert (slow.middleware, slow.throttle) == ((tenant, member), "1/minute")

        with pytest.raises(ValueError): Route.get("/x", items.index).constrained(key="regex")

        listed  = await bare.get("/v1/items")
        shown   = await bare.get("/v1/items/7")
        typed   = await bare.get("/v1/items/x/typed")
        stored  = await bare.post("/v1/items")
        removed = await bare.delete("/v1/items/7")
        put     = await bare.put("/v1/items")
        nowhere = await bare.get("/v1/nowhere")

        assert listed.status_code == 200 and listed.json()["data"] == [{ "id": 1 }]
        assert listed.headers["x-content-type-options"] == "nosniff"
        assert listed.json()["meta"] == {
            "request_id": listed.headers["x-request-id"], "page": 2, "limit": 20, "total": 41, "pages": 3,
        }
        assert shown.json()["data"] == { "id": 7 } and typed.status_code == 404
        assert (stored.status_code, stored.json()["code"]) == (201, "created")
        assert (removed.status_code, removed.json()["message"]) == (200, "removed 7")
        assert (put.status_code, put.json()["code"]) == (405, "method_not_allowed")
        assert (nowhere.status_code, nowhere.json()["code"], nowhere.json()["data"]) == (404, "not_found", None)
        assert (await bare.get("/openapi.json")).status_code == 404 and (await bare.get("/docs")).status_code == 404

    async def test_failures_are_enveloped_masked_and_traced ( self, bare: AsyncClient ) -> None:

        crashed = await bare.get("/v1/crash", headers={ "X-Request-Id": "trace-123" })
        mapped  = await bare.get("/v1/mistake")
        refused = await bare.get("/v1/refuse")
        rejected = await bare.get("/v1/private/me")
        admitted = await bare.get("/v1/private/me", headers={ "x-key": "open" })
        bogus    = await bare.get("/v1/items", headers={ "X-Request-Id": "bad id with spaces" })

        assert crashed.status_code == 500 and crashed.headers["x-request-id"] == "trace-123"
        assert crashed.json()["code"] == "internal" and "secret" not in crashed.text
        assert crashed.json()["meta"]["request_id"] == "trace-123"
        assert (mapped.status_code, mapped.json()["code"]) == (400, "bad_request") and "bad input" not in mapped.text
        assert (refused.status_code, refused.json()["reason"]) == (403, "not yours")
        assert (rejected.status_code, rejected.json()["reason"]) == (401, "key")
        assert admitted.json()["data"] == { "user": "keyholder" }
        assert bogus.headers["x-request-id"] != "bad id with spaces" and len(bogus.headers["x-request-id"]) == 36

    async def test_throttle_counts_per_scope_and_per_client ( self, bare: AsyncClient ) -> None:

        burst = [await bare.get("/v1/limited", headers=forwarded("10.1.0.1")) for _ in range(3)]
        other = await bare.get("/v1/also-limited", headers=forwarded("10.1.0.1"))
        fresh = await bare.get("/v1/limited", headers=forwarded("10.1.0.2"))

        assert [reply.status_code for reply in burst] == [200, 200, 429]
        assert [reply.headers["x-ratelimit-remaining"] for reply in burst] == ["1", "0", "0"]
        assert all(reply.headers["x-ratelimit-limit"] == "2" for reply in burst)
        assert float(burst[2].headers["x-ratelimit-reset"]) <= 60
        assert burst[2].json()["code"] == "too_many_requests" and burst[2].json()["reason"].startswith("retry in")
        assert other.status_code == 200 and fresh.status_code == 200

        inside   = { **forwarded("10.1.0.9"), "X-Tenant": "acme" }
        nobody   = await bare.get("/v1/tenants/acme/orders", headers=forwarded("10.1.0.9"))
        stranger = await bare.get("/v1/tenants/acme/orders", headers={ **forwarded("10.1.0.9"), "X-Tenant": "other" })
        allowed  = [await bare.get("/v1/tenants/acme/orders", headers=inside) for _ in range(4)]
        narrow   = [await bare.get("/v1/tenants/acme/slow", headers=inside) for _ in range(2)]

        assert (nobody.status_code, nobody.json()["reason"]) == (400, "tenant")
        assert (stranger.status_code, stranger.json()["reason"]) == (403, "tenant.member")
        assert [reply.status_code for reply in allowed] == [200, 200, 200, 429]
        assert allowed[3].headers["x-ratelimit-limit"] == "3" and "x-ratelimit-limit" not in nobody.headers
        assert [reply.status_code for reply in narrow] == [200, 429] and narrow[1].headers["x-ratelimit-limit"] == "1"

    async def test_cors_opens_only_to_listed_origins ( self, bare: AsyncClient ) -> None:

        headers = { "Access-Control-Request-Method": "GET" }
        allowed = await bare.options("/v1/items", headers={ **headers, "Origin": "http://web.test" })
        denied  = await bare.options("/v1/items", headers={ **headers, "Origin": "http://evil.test" })
        simple  = await bare.get("/v1/items", headers={ "Origin": "http://web.test" })

        assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == "http://web.test"
        assert "x-request-id" in simple.headers["access-control-expose-headers"].lower()
        assert denied.status_code == 400 and "access-control-allow-origin" not in denied.headers
        assert simple.headers["access-control-allow-origin"] == "http://web.test"

    async def test_application_serves_health_hello_validation_and_scalar_docs (
        self, client: AsyncClient, app: App,
    ) -> None:

        health  = await client.get("/health")
        hello   = await client.get("/v1/hello", params={ "name": "World" })
        guest   = await client.get("/v1/hello", params={ "name": "Nobody Here" })
        invalid = await client.get("/v1/hello", params={ "name": "x" * 33 })
        docs    = await client.get("/docs")
        icon    = await client.get("/assets/images/brand/icon.svg")
        robots  = await client.get("/robots.txt")
        hidden  = await client.get("/assets/../pyproject.toml")
        schema  = await client.get("/openapi.json")
        paths   = schema.json()["paths"]
        named   = { str(getattr(route, "name", "")) for route in app.routes }

        assert health.status_code == 200 and health.json()["data"]["status"] == "ok"
        assert health.json()["data"]["database"]["alive"] is True
        assert health.json()["data"]["checks"]["database"]["status"] == "ok"
        assert "llm" in health.json()["data"]["checks"]
        assert hello.json()["data"]["message"] == "Hello World"
        assert hello.json()["data"]["user"]["email"] == "world@ragx.test"
        assert guest.json()["data"] == { "message": "Hello Nobody Here", "user": None }
        assert invalid.status_code == 422 and list(invalid.json()["errors"]) == ["name"]
        assert docs.status_code == 200 and docs.headers["content-type"].startswith("text/html")
        assert "scalar" in docs.text.lower()
        assert schema.json()["info"]["title"] == app.title
        assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")
        assert icon.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert robots.status_code == 200 and "Disallow: /" in robots.text and hidden.status_code == 404
        assert { "/health", "/v1/hello", "/v1/auth/register", "/v1/auth/login" } <= set(paths)
        assert { "/v1/auth/refresh", "/v1/auth/logout", "/v1/auth/me" } <= set(paths)
        assert paths["/v1/auth/login"]["post"]["tags"] == ["auth"] and "docs" not in paths
        assert { "401", "422", "429", "500" } <= set(paths["/v1/auth/login"]["post"]["responses"])
        assert schema.json()["components"]["schemas"]["Envelope"]["required"][0] == "data"
        assert { "health", "v1.hello", "v1.auth.register", "v1.auth.login", "v1.auth.me" } <= named

async def echo ( payload: Incoming ) -> Response:

    return Response.ok({
        "all": payload.all(), "name": payload.text("name"), "n": payload.integer("n"), "flag": payload.boolean("flag"),
        "tags": payload.items("tags"), "has": payload.has("name", "n"), "filled": payload.filled("empty"),
        "bearer": payload.bearer(), "json": payload.is_json(), "route": payload.route_name(), "ip": payload.ip(),
        "only": payload.only("name"), "nested": payload.input("meta.deep"), "missing": payload.missing("zzz"),
        "without": sorted(payload.except_("name", "key", "n", "tags")), "wants": payload.wants_json(),
    })

async def ticks () -> EventStream:

    async def source () -> AsyncIterator[Sse | dict[str, object] | str]:

        yield Sse({ "n": 1 }, event="tick", id="1")
        yield { "data": "two", "event": "tick" }
        yield "three"

    return Response.sse(source(), ping=0)

async def rows () -> Streamed:
    return Response.ndjson([{ "a": 1 }, { "b": 2 }])

async def gone () -> Redirect:
    return Response.redirect("/v2/items", 308)

async def shaped ( payload: Incoming ) -> Response:
    return Response.ok(payload.shape(name=str, age=int))

async def required ( payload: Incoming ) -> Response:
    return Response.ok(payload.require("name"))

async def lost ( payload: Incoming ) -> Response:
    return Response.problem(Code.NOT_FOUND, payload.param("fallback"))

async def probe ( payload: Incoming ) -> Response:

    day = payload.date("day")

    return Response.with_cookie(Response.ok({
        "agent": payload.user_agent(), "ips": payload.ips(), "is": payload.is_("d/probe*"),
        "route": payload.route_is("d.pr*"), "day": day.isoformat() if day else None,
        "merged": payload.merge(x=1).input("x"), "has": payload.when_has("name", str.upper, "none"),
        "filled": payload.when_filled("empty", str.upper, "blank"), "file": payload.has_file("upload"),
    }), "seen", "1", max_age=60)

async def pulled () -> Streamed:

    async def chunks () -> AsyncIterator[bytes]:
        yield b"abc"

    return Response.stream_download(chunks(), "dump.bin")

async def tenant_home ( request: Request ) -> Response:
    return Response.ok(request.state.domain)

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
    Route.post("/required", required, name="required"),
    Route.redirect("/old", "/d/rows", name="old"),
    Route.permanent_redirect("/older", "/d/rows", name="older"),
    Route.post("/probe", probe, name="probe"),
    Route.get("/pulled", pulled, name="pulled"),
], name="d")

@pytest.mark.anyio
class TestDsl:

    async def test_payload_router_and_streaming_responses ( self ) -> None:

        app    = http.build("Dsl", "0.0.1", [dsl])
        router = http.router(app)

        assert router.url("d.echo", key=7, page=2) == "/d/echo/7?page=2" and http.url("d.rows") == "/d/rows"
        assert router.params("d.echo") == ["key"] and router.has("d.gone") and not http.has("nowhere")
        assert router.methods("/d/rows") == ["GET"] and len(router.by_prefix("/d")) == 10
        assert router.names()[0] == "d.echo"
        assert router.describe()[0]["name"] == "d.echo" and router.find("d.old").methods == ("GET",)
        things = Route.resource("/things", items, except_=("destroy",))

        assert things.names() == ["things.index", "things.store", "things.show"]
        assert Route.get("/x", items.index).tagged("a", "b").tags == ("a", "b") and dsl.find("d.rows") is not None
        assert "/d/rows" in dsl.paths() and Response.problem(Code.CONFLICT, "dup").status_code == 409
        assert Response.no_content().status_code == 204 and Response.json({ "a": 1 }, 202).status_code == 202
        assert Response.with_headers(Response.ok(), x_custom="1").headers["x-custom"] == "1"
        assert Response.text("hi").media_type == "text/plain"
        assert Response.raw(b"x").media_type == "application/octet-stream"

        with pytest.raises(Fault): router.url("d.echo")
        with pytest.raises(Fault): router.url("nowhere")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://dsl") as client:

            sent = await client.post(
                "/d/echo/9", params={ "n": "5", "tags[]": ["a", "b"] },
                json={ "name": " Ann ", "flag": "yes", "empty": "", "meta": { "deep": 1 } },
                headers={ "Authorization": "Bearer tok", "X-Forwarded-For": "10.0.0.7" },
            )
            data = sent.json()["data"]

            assert data["name"] == "Ann" and data["n"] == 5 and data["flag"] is True and data["tags"] == ["a", "b"]
            assert data["has"] and not data["filled"] and data["bearer"] == "tok" and data["json"] and data["wants"]
            assert data["route"] == "d.echo" and data["ip"] == "10.0.0.7" and data["only"] == { "name": " Ann " }
            assert data["nested"] == 1 and data["all"]["key"] == "9" and data["missing"]
            assert data["without"] == ["empty", "flag", "meta"]

            formed  = await client.post("/d/shaped", data={ "name": "Bo", "age": "3" })
            broken  = await client.post("/d/echo/1", content=b"{bad", headers={ "content-type": "application/json" })
            lacking = await client.post("/d/required", json={})
            invalid = await client.post("/d/shaped", json={ "name": "Bo", "age": "x" })
            events  = await client.get("/d/events")
            lines   = await client.get("/d/rows")
            moved   = await client.get("/d/gone")
            old     = await client.get("/d/old")

            assert formed.json()["data"] == { "name": "Bo", "age": 3 }
            assert (broken.status_code, broken.json()["reason"]) == (400, "json")
            assert (lacking.status_code, list(lacking.json()["errors"])) == (422, ["name"])
            assert (invalid.status_code, list(invalid.json()["errors"])) == (422, ["age"])
            assert events.headers["content-type"].startswith("text/event-stream")
            assert events.headers["cache-control"] == "no-cache"
            assert events.text == 'event: tick\nid: 1\ndata: {"n":1}\n\nevent: tick\ndata: two\n\ndata: three\n\n'
            assert lines.text == '{"a":1}\n{"b":2}\n' and lines.headers["content-type"] == "application/x-ndjson"
            assert (moved.status_code, moved.headers["location"]) == (308, "/v2/items")
            assert (old.status_code, old.headers["location"]) == (307, "/d/rows")

            older  = await client.get("/d/older")
            probed = await client.post(
                "/d/probe", params={ "day": "2026-01-02", "name": "ann", "empty": "" },
                headers={ "User-Agent": "unit/1", "X-Forwarded-For": "10.0.0.1, 10.0.0.2" },
            )
            pulled = await client.get("/d/pulled")
            facts  = probed.json()["data"]

            assert (older.status_code, older.headers["location"]) == (308, "/d/rows")
            assert facts["agent"] == "unit/1" and facts["ips"][:2] == ["10.0.0.1", "10.0.0.2"]
            assert facts["is"] and facts["route"] and facts["day"].startswith("2026-01-02") and facts["merged"] == 1
            assert facts["has"] == "ANN" and facts["filled"] == "blank" and facts["file"] is False
            assert probed.cookies["seen"] == "1" and pulled.content == b"abc"
            assert pulled.headers["content-disposition"] == 'attachment; filename="dump.bin"'

        hosted = http.build("Hosts", "0.0.1", [hosts])

        assert hosted.state.router.names() == ["h.home", "h.t.x", "h.fallback"]

        async with AsyncClient(transport=ASGITransport(app=hosted), base_url="http://acme.api.test") as client:

            home    = await client.get("/h/home")
            nowhere = await client.get("/h/anything/here")
            foreign = await client.get("/h/t/x")

            assert home.json()["data"] == { "tenant": "acme" }
            assert (nowhere.status_code, nowhere.json()["reason"]) == (404, "anything/here")
            assert (foreign.status_code, foreign.json()["reason"]) == (404, "domain")

        async with AsyncClient(transport=ASGITransport(app=hosted), base_url="http://www.api.test") as client:

            assert (await client.get("/h/t/x")).status_code == 200
            assert (await client.get("/h/home")).json()["data"] == { "tenant": "www" }

        async with AsyncClient(transport=ASGITransport(app=hosted), base_url="http://nope.test") as client:

            assert (await client.get("/h/home")).json()["reason"] == "domain"
