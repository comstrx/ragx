from engine.http import App
from engine.test import Client, expect

class TestApplication:

    async def test_the_bare_framework_serves_health_docs_and_assets_only ( self, client: Client, app: App ) -> None:

        health = (await client.get("/health")).ok()
        schema = (await client.get("/openapi.json")).ok()
        paths  = schema.json()["paths"]

        expect(health.data()).subset({
            "status": "ok", "database": { "alive": True }, "checks": { "database": { "status": "ok" } },
        })
        expect(health.data("checks")).keys("cache", "database", "events", "llm", "queue", "storage")

        (await client.get("/assets/../pyproject.toml")).status(404)
        (await client.get("/v1/hello")).status(404)

        docs   = (await client.get("/docs")).ok()
        icon   = (await client.get("/assets/images/brand/icon.svg")).ok()
        robots = (await client.get("/robots.txt")).ok()

        expect(docs.headers["content-type"]).starts_with("text/html")
        expect(docs.text().lower()).contains("scalar")
        expect(icon.headers["content-type"]).starts_with("image/svg+xml")
        expect(icon.headers["cache-control"]).equals("public, max-age=31536000, immutable")
        expect(robots.text()).contains("Disallow: /")
        expect(schema.json()["info"]["title"]).equals(app.title())
        expect(sorted(paths)).equals(["/health"])
        expect(paths["/health"]["get"]["tags"]).equals(["health"])
        expect(schema.json()["components"]["schemas"]["Envelope"]["required"][0]).equals("data")
        expect(app.names()).contains("health")
