from httpx import AsyncClient
import pytest


@pytest.mark.anyio
class TestCors:

    async def test_a_web_origin_may_call_and_read_the_request_id ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/hello", headers={"Origin": "http://localhost:3000"})

        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "x-request-id" in response.headers["access-control-expose-headers"].lower()

    async def test_a_preflight_is_answered_for_a_known_origin_only ( self, client: AsyncClient ) -> None:

        headers = {
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-request-id",
        }
        allowed = await client.options("/v1/hello", headers=headers)
        refused = await client.options("/v1/hello", headers={**headers, "Origin": "https://evil.example"})

        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert "access-control-allow-origin" not in refused.headers
