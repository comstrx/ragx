from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from core.database import Statement, database
from core.error import Fault, Faults
from core.http import App, Response, Route, http
from app.repositories import users
import pytest

faults = Faults()


class BoomController:

    async def crash ( self ) -> Response:
        raise RuntimeError("secret detail")

    async def refuse ( self ) -> Response:
        raise faults.forbidden("not yours")


@pytest.fixture
async def broken () -> AsyncIterator[AsyncClient]:

    boom = BoomController()
    app  = http.build("Broken", "0.0.0", [Route.group("", [
        Route.get("/crash", boom.crash),
        Route.get("/refuse", boom.refuse),
    ])])

    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://api") as client:
        yield client


@pytest.mark.anyio
class TestErrors:

    async def test_unknown_route_is_a_not_found_envelope ( self, client: AsyncClient ) -> None:

        response = await client.get("/v1/nothing")
        body     = response.json()

        assert response.status_code == 404
        assert body["code"] == "not_found"
        assert body["message"] == "The resource was not found"
        assert body["meta"]["request_id"] == response.headers["x-request-id"]

    async def test_wrong_method_is_a_method_not_allowed_envelope ( self, client: AsyncClient ) -> None:

        response = await client.post("/v1/hello")

        assert response.status_code == 405
        assert response.json()["code"] == "method_not_allowed"

    async def test_a_raised_fault_keeps_its_reason ( self, broken: AsyncClient ) -> None:

        response = await broken.get("/refuse")
        body     = response.json()

        assert response.status_code == 403
        assert body["code"] == "forbidden"
        assert body["reason"] == "not yours"

    async def test_an_unexpected_exception_never_leaks ( self, broken: AsyncClient ) -> None:

        response = await broken.get("/crash")
        body     = response.json()

        assert response.status_code == 500
        assert body["code"] == "internal"
        assert body["reason"] is None
        assert "secret" not in response.text
        assert response.headers["x-request-id"] == body["meta"]["request_id"]

    async def test_a_database_failure_arrives_as_the_same_envelope (
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
    ) -> None:

        async def gone ( _: str ) -> None:
            raise faults.unavailable("database")

        monkeypatch.setattr(users, "find_by_name", gone)

        response = await client.get("/v1/hello")
        body     = response.json()

        assert response.status_code == 503
        assert body["code"] == "unavailable"
        assert body["reason"] == "database"
        assert body["data"] is None
        assert response.headers["x-request-id"] == body["meta"]["request_id"]

    async def test_a_broken_statement_is_a_fault_not_a_driver_error ( self, app: App ) -> None:

        with pytest.raises(Fault) as missing: await database.fetch(Statement('SELECT * FROM "nowhere"'))
        with pytest.raises(Fault) as malformed: await database.fetch(Statement("SELECT $1::int", ("x",)))

        assert missing.value.code == "internal"
        assert missing.value.reason == "database"
        assert malformed.value.code == "validation"
