from core.database import database
from core.date import date
from core.error import Code
from core.mail import LogMailer
from core.queue import queue
from core.rand import rand
from core.string import string
from core.test import Client, expect
from core.thread import thread
from app.enums import TokenKind
from app.repositories import tokens, users
from app.utils.dna import passwords

LIFE  = { "X-Forwarded-For": "10.9.0.1" }
BURST = { "X-Forwarded-For": "10.9.0.2" }
SPARE = { "X-Forwarded-For": "10.9.0.3" }

def bearer ( text: str ) -> dict[str, str]:

    return { **LIFE, "Authorization": f"Bearer {text}" }

def tampered ( jwt: str ) -> list[str]:

    head, body, signature = jwt.split(".")
    none   = string.to_base64('{"alg":"none","typ":"JWT"}', url=True).rstrip("=")
    forged = signature[:-2] + ("AA" if signature[-2:] != "AA" else "BB")

    return [f"{head}.{body}.{forged}", f"{none}.{body}.", f"{head}.{body}", f"{head}.{body[::-1]}.{signature}"]

class TestAuth:

    async def test_register_login_refresh_logout_lifecycle_with_rotation (
        self, client: Client, outbox: LogMailer,
    ) -> None:

        tag      = rand.hex(4)
        email    = f"ada-{tag}@unit.test"
        password = f"Str0ng-{tag}-pass"
        body     = { "name": f"Ada {tag}", "email": email.upper(), "password": password }
        created  = (await client.post("/v1/auth/register", json=body, headers=LIFE)).created()
        session  = created.data()
        silent   = outbox.last()
        worked   = await queue.drain()
        welcome  = outbox.last()

        expect(created.json()["code"]).equals("created")
        expect((silent, worked >= 1)).equals((None, True))
        expect(set(session)).equals({ "token_type", "access_token", "expires_in", "refresh_token", "user" })
        expect(session).subset({
            "token_type": "bearer", "expires_in": 900, "user": { "email": email, "roles": ["client"] },
        })
        expect(session["user"]).lacks("password")
        expect(welcome).some().satisfies(lambda mail: mail.recipients == (email,))
        expect(welcome.subject if welcome else None).equals(f"Welcome to RagX, Ada {tag}")
        expect(welcome.markup if welcome else "").contains(f"Ada {tag}")
        expect(welcome.body if welcome else "").contains("RagX")

        common = { **body, "email": f"w-{tag}@unit.test", "password": "password" }
        broken = { "name": "", "email": "nope", "password": "short" }

        (await client.post("/v1/auth/register", json=body, headers=LIFE)).fault(Code.CONFLICT).expect("errors").equals(
            { "email": [f"{email} is already registered"] },
        )
        (await client.post("/v1/auth/register", json=common, headers=LIFE)).fault(Code.VALIDATION, field="password")
        (await client.post("/v1/auth/register", json=broken, headers=LIFE)).fault(Code.VALIDATION).expect(
            "errors",
        ).keys("email", "name", "password")

        bad    = { "email": email, "password": "wrong-password" }
        nobody = { "email": f"ghost-{tag}@unit.test", "password": password }
        logged = await client.post("/v1/auth/login", json={ "email": email, "password": password }, headers=LIFE)
        pair   = logged.ok().data()

        (await client.post("/v1/auth/login", json=bad, headers=LIFE)).fault(Code.UNAUTHORIZED, "credentials")
        (await client.post("/v1/auth/login", json=nobody, headers=LIFE)).fault(Code.UNAUTHORIZED, "credentials")

        expect(pair["access_token"]).differs(session["access_token"])

        for headers, reason in (
            (LIFE, "token.missing"),
            (bearer("garbage"), "token"),
            (bearer(pair["refresh_token"]), "token.kind"),
            *((bearer(forged), "token") for forged in tampered(pair["access_token"])),
        ):

            (await client.get("/v1/auth/me", headers=headers)).fault(Code.UNAUTHORIZED, reason)

        me      = (await client.get("/v1/auth/me", headers=bearer(pair["access_token"]))).ok()
        rotated = await client.post("/v1/auth/refresh", json={ "refresh_token": pair["refresh_token"] }, headers=LIFE)
        fresh   = rotated.ok().data()
        replay  = await client.post("/v1/auth/refresh", json={ "refresh_token": pair["refresh_token"] }, headers=LIFE)
        crossed = await client.post("/v1/auth/refresh", json={ "refresh_token": fresh["access_token"] }, headers=LIFE)

        expect(me.data()).subset({ "email": email, "roles": ["client"] })
        expect(fresh["refresh_token"]).differs(pair["refresh_token"])

        replay.fault(Code.UNAUTHORIZED, "token.revoked")
        crossed.fault(Code.UNAUTHORIZED, "token.kind")

        owner = bearer(fresh["access_token"])

        (await client.post("/v1/auth/logout", json={ "refresh_token": pair["refresh_token"] }, headers=owner)).fault(
            Code.UNAUTHORIZED, "token.revoked",
        )
        (await client.post("/v1/auth/logout", json={ "refresh_token": fresh["refresh_token"] }, headers=owner)).ok()
        (await client.post("/v1/auth/refresh", json={ "refresh_token": fresh["refresh_token"] }, headers=LIFE)).fault(
            Code.UNAUTHORIZED,
        )
        (await client.get("/v1/auth/me", headers=owner)).ok()

        user   = await users.find_by_email(email)
        owned  = tokens.query().where("owner_id", user.id if user else None)
        stored = await owned.where("kind", TokenKind.REFRESH.value).get()
        raws   = { session["refresh_token"], pair["refresh_token"], fresh["refresh_token"] }

        expect(user).some()
        expect(stored).length(3).each(lambda token: len(token.hash) == 64)
        expect(sum(token.revoked_at is None for token in stored)).equals(1)
        expect({ token.hash for token in stored }.isdisjoint(raws)).true()

    async def test_register_is_throttled_per_client_before_validation ( self, client: Client ) -> None:

        statuses = [(await client.post("/v1/auth/register", json={}, headers=BURST)).code for _ in range(10)]
        blocked  = await client.post("/v1/auth/register", json={}, headers=BURST)

        expect(statuses).equals([422] * 10)

        blocked.fault(Code.TOO_MANY_REQUESTS).header("x-ratelimit-limit", "10").header("x-ratelimit-remaining", "0")

        (await client.post("/v1/auth/register", json={}, headers=SPARE)).fault(Code.VALIDATION)

    async def test_a_refresh_token_rotates_once_even_under_a_race ( self, client: Client ) -> None:

        tag     = rand.hex(4)
        body    = { "name": f"Race {tag}", "email": f"race-{tag}@unit.test", "password": f"Str0ng-{tag}-pass" }
        session = (await client.post("/v1/auth/register", json=body, headers=SPARE)).created().data()

        expect(await database.fill(6)).equals(6)
        sent    = { "refresh_token": session["refresh_token"] }
        raced   = await thread.gather(*(client.post("/v1/auth/refresh", json=sent, headers=SPARE) for _ in range(4)))

        expect(sorted(reply.code for reply in raced)).equals([200, 401, 401, 401])
        refused = [reply.json()["reason"] for reply in raced if reply.code == 401]

        expect(refused).equals(["token.revoked"] * 3)

    async def test_unknown_emails_cost_the_same_hash_as_wrong_passwords ( self, client: Client ) -> None:

        tag  = rand.hex(4)
        body = { "name": f"Time {tag}", "email": f"time-{tag}@unit.test", "password": f"Str0ng-{tag}-pass" }

        (await client.post("/v1/auth/register", json=body, headers=SPARE)).created()

        expect(await passwords.verify("anything", None)).false()
        expect(await passwords.decoy()).starts_with("$argon2id$")

        async def timed ( email: str ) -> float:

            started = date.tick()

            attempt = { "email": email, "password": "Wrong-pass-1" }

            (await client.post("/v1/auth/login", json=attempt, headers=SPARE)).fault(Code.UNAUTHORIZED, "credentials")

            return date.elapsed(started)

        ghost = min([await timed(f"ghost-{tag}@unit.test") for _ in range(3)])
        known = min([await timed(body["email"]) for _ in range(3)])

        expect(ghost / known).between(0.5, 2.0)
