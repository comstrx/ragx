from core.database import database
from httpx import AsyncClient
import pytest


@pytest.mark.anyio
class TestHealth:

    async def test_answers_with_the_release_facts_and_the_pool ( self, client: AsyncClient ) -> None:

        response = await client.get("/health")
        body     = response.json()

        assert response.status_code == 200
        assert body["code"] == "ok"
        assert body["data"]["status"] == "ok"
        assert body["data"]["version"] == "0.1.0"
        assert body["data"]["release"] is None
        assert body["data"]["database"]["alive"] is True
        assert body["data"]["database"]["ready"] is True
        assert body["data"]["database"]["max"] == 10

    async def test_degrades_to_unavailable_when_the_database_is_gone (
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:

        async def dead () -> bool:
            return False

        monkeypatch.setattr(database, "ping", dead)

        response = await client.get("/health")
        body     = response.json()

        assert response.status_code == 503
        assert body["code"] == "unavailable"
        assert body["reason"] == "database"
        assert body["meta"]["health"]["status"] == "degraded"
