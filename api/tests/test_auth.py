from httpx import AsyncClient
from core.mail import MemoryTransport
from core.queue import queue
from core.rand import rand
from app.enums import TokenKind
from app.repositories import tokens, users
import pytest

LIFE  = { "X-Forwarded-For": "10.9.0.1" }
BURST = { "X-Forwarded-For": "10.9.0.2" }
SPARE = { "X-Forwarded-For": "10.9.0.3" }

def bearer ( text: str ) -> dict[str, str]:
    return { **LIFE, "Authorization": f"Bearer {text}" }

@pytest.mark.anyio
class TestAuth:

    async def test_register_login_refresh_logout_lifecycle_with_rotation (
        self, client: AsyncClient, outbox: MemoryTransport,
    ) -> None:

        tag      = rand.hex(4)
        email    = f"ada-{tag}@unit.test"
        password = f"Str0ng-{tag}-pass"
        body     = { "name": f"Ada {tag}", "email": email.upper(), "password": password }

        created = await client.post("/v1/auth/register", json=body, headers=LIFE)
        session = created.json()["data"]
        silent  = outbox.last()
        worked  = await queue.drain()
        welcome = outbox.last()

        assert (created.status_code, created.json()["code"]) == (201, "created")
        assert silent is None and worked >= 1
        assert set(session) == { "token_type", "access_token", "expires_in", "refresh_token", "user" }
        assert session["token_type"] == "bearer" and session["expires_in"] == 900
        assert session["user"]["email"] == email and session["user"]["roles"] == ["client"]
        assert "password" not in session["user"]
        assert welcome is not None and welcome.to == (email,) and welcome.subject == f"Welcome to RagX, Ada {tag}"
        assert welcome.html and f"Ada {tag}" in welcome.html and welcome.text and "RagX" in welcome.text

        duplicate = await client.post("/v1/auth/register", json=body, headers=LIFE)
        common    = { **body, "email": f"w-{tag}@unit.test", "password": "password" }
        broken    = { "name": "", "email": "nope", "password": "short" }
        weak      = await client.post("/v1/auth/register", json=common, headers=LIFE)
        malformed = await client.post("/v1/auth/register", json=broken, headers=LIFE)

        assert duplicate.status_code == 409
        assert duplicate.json()["errors"] == { "email": [f"{email} is already registered"] }
        assert weak.status_code == 422 and list(weak.json()["errors"]) == ["password"]
        assert malformed.status_code == 422 and sorted(malformed.json()["errors"]) == ["email", "name", "password"]

        bad    = { "email": email, "password": "wrong-password" }
        nobody = { "email": f"ghost-{tag}@unit.test", "password": password }
        wrong  = await client.post("/v1/auth/login", json=bad, headers=LIFE)
        ghost  = await client.post("/v1/auth/login", json=nobody, headers=LIFE)
        logged = await client.post("/v1/auth/login", json={ "email": email, "password": password }, headers=LIFE)
        pair   = logged.json()["data"]

        assert (wrong.status_code, wrong.json()["reason"]) == (401, "credentials")
        assert (ghost.status_code, ghost.json()["reason"]) == (401, "credentials")
        assert logged.status_code == 200 and pair["access_token"] != session["access_token"]

        for headers, reason in (
            (LIFE, "token.missing"),
            (bearer("garbage"), "token"),
            (bearer(pair["refresh_token"]), "token.kind"),
        ):

            denied = await client.get("/v1/auth/me", headers=headers)

            assert (denied.status_code, denied.json()["reason"]) == (401, reason)

        me      = await client.get("/v1/auth/me", headers=bearer(pair["access_token"]))
        rotated = await client.post("/v1/auth/refresh", json={ "refresh_token": pair["refresh_token"] }, headers=LIFE)
        fresh   = rotated.json()["data"]
        replay  = await client.post("/v1/auth/refresh", json={ "refresh_token": pair["refresh_token"] }, headers=LIFE)
        crossed = await client.post("/v1/auth/refresh", json={ "refresh_token": fresh["access_token"] }, headers=LIFE)

        assert me.status_code == 200 and me.json()["data"]["email"] == email
        assert me.json()["data"]["roles"] == ["client"]
        assert rotated.status_code == 200 and fresh["refresh_token"] != pair["refresh_token"]
        assert (replay.status_code, replay.json()["reason"]) == (401, "token.revoked")
        assert (crossed.status_code, crossed.json()["reason"]) == (401, "token.kind")

        owner = bearer(fresh["access_token"])
        stale = await client.post("/v1/auth/logout", json={ "refresh_token": pair["refresh_token"] }, headers=owner)
        out   = await client.post("/v1/auth/logout", json={ "refresh_token": fresh["refresh_token"] }, headers=owner)
        again = await client.post("/v1/auth/refresh", json={ "refresh_token": fresh["refresh_token"] }, headers=LIFE)
        still = await client.get("/v1/auth/me", headers=owner)

        assert (stale.status_code, stale.json()["reason"]) == (401, "token.revoked")
        assert out.status_code == 200 and again.status_code == 401 and still.status_code == 200

        user   = await users.find_by_email(email)
        owned  = tokens.query().where("owner_id", user.id if user else None)
        stored = await owned.where("kind", TokenKind.REFRESH.value).get()
        raws   = { session["refresh_token"], pair["refresh_token"], fresh["refresh_token"] }

        assert user is not None and len(stored) == 3 and sum(token.revoked_at is None for token in stored) == 1
        assert all(len(token.hash) == 64 for token in stored)
        assert { token.hash for token in stored }.isdisjoint(raws)

    async def test_register_is_throttled_per_client_before_validation ( self, client: AsyncClient ) -> None:

        statuses = [(await client.post("/v1/auth/register", json={}, headers=BURST)).status_code for _ in range(10)]
        blocked  = await client.post("/v1/auth/register", json={}, headers=BURST)
        other    = await client.post("/v1/auth/register", json={}, headers=SPARE)

        assert statuses == [422] * 10
        assert (blocked.status_code, blocked.json()["code"]) == (429, "too_many_requests")
        assert blocked.headers["x-ratelimit-limit"] == "10" and blocked.headers["x-ratelimit-remaining"] == "0"
        assert other.status_code == 422
