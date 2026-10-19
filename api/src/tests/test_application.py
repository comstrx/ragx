from core.error import Code
from core.http import App
from core.test import Client, expect

class TestApplication:

    async def test_application_serves_health_hello_validation_and_scalar_docs (
        self, client: Client, app: App,
    ) -> None:

        health = (await client.get("/health")).ok()
        schema = (await client.get("/openapi.json")).ok()
        paths  = schema.json()["paths"]

        expect(health.data()).subset({
            "status": "ok", "database": { "alive": True }, "checks": { "database": { "status": "ok" } },
        })
        expect(health.data("checks")).contains("llm")
        expect((await client.get("/v1/hello", params={ "name": "World" })).data()).subset({
            "message": "Hello World", "user": { "email": "world@ragx.test" },
        })
        expect((await client.get("/v1/hello", params={ "name": "Nobody Here" })).data()).equals(
            { "message": "Hello Nobody Here", "user": None },
        )
        expect((await client.get("/v1/hello")).data("message")).equals("Hello World")

        (await client.get("/v1/hello", params={ "name": "x" * 33 })).fault(Code.VALIDATION, field="name")
        (await client.get("/assets/../pyproject.toml")).status(404)

        docs   = (await client.get("/docs")).ok()
        icon   = (await client.get("/assets/images/brand/icon.svg")).ok()
        robots = (await client.get("/robots.txt")).ok()

        expect(docs.headers["content-type"]).starts_with("text/html")
        expect(docs.text().lower()).contains("scalar")
        expect(icon.headers["content-type"]).starts_with("image/svg+xml")
        expect(icon.headers["cache-control"]).equals("public, max-age=31536000, immutable")
        expect(robots.text()).contains("Disallow: /")
        expect(schema.json()["info"]["title"]).equals(app.title())
        expect(paths).contains("/health", "/v1/hello", "/v1/auth/register", "/v1/auth/login", "/v1/auth/refresh")
        expect(paths).contains("/v1/auth/logout", "/v1/auth/me").lacks("docs", "/robots.txt")
        expect(paths["/v1/hello"]["get"]["parameters"][0]).subset({ "name": "name", "in": "query", "required": False })
        expect(paths["/v1/auth/login"]["post"]["tags"]).equals(["auth"])
        expect(paths["/v1/auth/login"]["post"]["responses"]).contains("401", "422", "429", "500")
        expect(schema.json()["components"]["schemas"]["Envelope"]["required"][0]).equals("data")
        expect(app.names()).contains("health", "v1.hello", "v1.auth.register", "v1.auth.login", "v1.auth.me")
