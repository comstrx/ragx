from uuid import UUID

from httpx import AsyncClient
import pytest

ENVELOPE = {"data", "message", "errors", "code", "reason", "meta"}


@pytest.mark.anyio
class TestHello:

    async def test_greets_the_world_through_every_layer_inside_the_envelope ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/hello")
        body     = response.json()

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert set(body) == ENVELOPE
        assert body["data"]["message"] == "Hello World"
        assert body["data"]["user"]["name"] == "World"
        assert body["data"]["user"]["role"] == "client"
        assert UUID(body["data"]["user"]["id"]).version == 7
        assert set(body["data"]["user"]) == {"id", "name", "role", "created_at"}
        assert body["code"] == "ok"
        assert body["message"] is None
        assert body["errors"] is None
        assert body["reason"] is None
        assert UUID(body["meta"]["request_id"]).version == 7
        assert response.headers["x-request-id"] == body["meta"]["request_id"]

    async def test_greets_a_stranger_without_inventing_a_user ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/hello", params={"name": "RagX"})

        assert response.json()["data"] == {"message": "Hello RagX", "user": None}

    async def test_keeps_a_valid_incoming_request_id ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/hello", headers={"X-Request-Id": "trace-42"})

        assert response.headers["x-request-id"] == "trace-42"
        assert response.json()["meta"]["request_id"] == "trace-42"

    async def test_replaces_a_hostile_incoming_request_id ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/hello", headers={"X-Request-Id": "bad id\twith\nbreaks"})

        assert UUID(response.headers["x-request-id"]).version == 7

    async def test_rejects_a_hostile_name_and_an_unknown_field ( self, client: AsyncClient ) -> None:

        hostile  = await client.get("/v1/hello", params={"name": "<script>" + "x" * 40})
        stranger = await client.get("/v1/hello", params={"name": "ok", "admin": "1"})

        assert hostile.status_code == 422
        assert hostile.json()["code"] == "validation"
        assert hostile.json()["data"] is None
        assert list(hostile.json()["errors"]) == ["name"]
        assert stranger.status_code == 422
        assert "admin" in stranger.json()["errors"]

    async def test_documents_itself ( self, client: AsyncClient ) -> None:

        spec = await client.get("/openapi.json")
        docs = await client.get("/docs")

        assert spec.status_code == 200
        assert "/v1/hello" in spec.json()["paths"]
        assert docs.status_code == 200
        assert docs.headers["content-type"].startswith("text/html")
        assert "/openapi.json" in docs.text
