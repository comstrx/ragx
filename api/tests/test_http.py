from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from core.exceptions import Code, Fault, Faults, exceptions
from core.http import App, Request, Response, Route, http
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

    exceptions.use(ExceptionHandler())

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
        assert listed.json()["meta"] == {
            "request_id": listed.headers["x-request-id"], "page": 2, "limit": 20, "total": 41, "pages": 3,
        }
        assert shown.json()["data"] == { "id": 7 } and typed.status_code == 404
        assert (stored.status_code, stored.json()["code"]) == (201, "created")
        assert (removed.status_code, removed.json()["message"]) == (200, "removed 7")
        assert (put.status_code, put.json()["code"]) == (405, "method_not_allowed")
        assert (nowhere.status_code, nowhere.json()["code"], nowhere.json()["data"]) == (404, "not_found", None)

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
        schema  = await client.get("/openapi.json")
        paths   = schema.json()["paths"]
        named   = { str(getattr(route, "name", "")) for route in app.routes }

        assert health.status_code == 200 and health.json()["data"]["status"] == "ok"
        assert health.json()["data"]["database"]["alive"] is True
        assert hello.json()["data"]["message"] == "Hello World"
        assert hello.json()["data"]["user"]["email"] == "world@ragx.test"
        assert guest.json()["data"] == { "message": "Hello Nobody Here", "user": None }
        assert invalid.status_code == 422 and list(invalid.json()["errors"]) == ["name"]
        assert docs.status_code == 200 and docs.headers["content-type"].startswith("text/html")
        assert "scalar" in docs.text.lower()
        assert schema.json()["info"]["title"] == app.title
        assert { "/health", "/v1/hello", "/v1/auth/register", "/v1/auth/login" } <= set(paths)
        assert { "/v1/auth/refresh", "/v1/auth/logout", "/v1/auth/me" } <= set(paths)
        assert paths["/v1/auth/login"]["post"]["tags"] == ["auth"] and "docs" not in paths
        assert { "401", "422", "429", "500" } <= set(paths["/v1/auth/login"]["post"]["responses"])
        assert schema.json()["components"]["schemas"]["Envelope"]["required"][0] == "data"
        assert { "health", "v1.hello", "v1.auth.register", "v1.auth.login", "v1.auth.me" } <= named
