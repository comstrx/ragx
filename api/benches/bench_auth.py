from dataclasses import dataclass
from typing import ClassVar

from core.crypto import crypto
from core.database import Blueprint, Model, Query, Schema, database
from core.date import DateTime, date
from core.error import Code, Fault
from core.http import Request, Response, Route
from core.rand import Uuid, rand
from core.thread import thread
from core.token import token
from core.validate import Email, Password, Shape, field
from benches import Bench
import asyncio

SUFFIX = rand.hex(3)

@dataclass(frozen=True, slots=True, kw_only=True)
class Member(Model):

    table      : ClassVar[str] = f"scratch_bench_members_{SUFFIX}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id       : Uuid
    email    : str
    password : str

@dataclass(frozen=True, slots=True, kw_only=True)
class Grant(Model):

    table      : ClassVar[str] = f"scratch_bench_grants_{SUFFIX}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id         : Uuid
    owner_id   : Uuid
    hash       : str
    expires_at : DateTime
    revoked_at : DateTime | None = None

class Credentials(Shape):

    email    : Email
    password : Password

class Rotation(Shape):

    refresh_token : str = field(min_length=16, max_length=4096)

def members () -> Query[Member]:

    return Query(Member, database)

def grants () -> Query[Grant]:

    return Query(Grant, database)

async def session ( member: Member ) -> dict[str, object]:

    access, _       = token.issue(str(member.id), "access", 900)
    refresh, issued = token.issue(str(member.id), "refresh", 86_400)

    await grants().create({ "owner_id": member.id, "hash": token.fingerprint(refresh), "expires_at": issued.expires })

    return { "access_token": access, "refresh_token": refresh, "user": { "id": str(member.id), "email": member.email } }

async def login ( body: Credentials ) -> Response:

    found = await members().where("email", body.email).first()
    known = await thread.offload(crypto.verify, body.password, found.password if found else DECOY)

    if found is None or not known: raise Fault(Code.UNAUTHORIZED, reason="credentials")

    return Response.ok(await session(found))

async def me ( request: Request ) -> Response:

    claims = token.verify(token.bearer(request.header("authorization")), kind="access")
    found  = await members().find(Uuid(claims.subject))

    if found is None: raise Fault(Code.UNAUTHORIZED, reason="user")

    return Response.ok({ "id": str(found.id), "email": found.email })

async def refresh ( body: Rotation ) -> Response:

    claims = token.verify(body.refresh_token, kind="refresh")
    alive  = grants().where("hash", token.fingerprint(body.refresh_token)).where_null("revoked_at")

    async with database.transaction():

        if await alive.update({ "revoked_at": date.now() }) != 1: raise Fault(Code.UNAUTHORIZED, reason="token.revoked")

        return Response.ok(await session(await members().find_or_fail(Uuid(claims.subject))))

def member ( table: Blueprint ) -> None:

    table.id()
    table.string("email", 254).unique()
    table.string("password", 255)

def grant ( table: Blueprint ) -> None:

    table.id()
    table.uuid("owner_id").index()
    table.string("hash", 128).unique()
    table.timestamp("expires_at")
    table.timestamp("revoked_at").nullable()

DECOY = crypto.hash("bench-decoy-password")

class AuthBench(Bench):

    logins      = 200
    reads       = 3000
    refreshes   = 300
    concurrency = 8

    async def run ( self ) -> None:

        routes = (
            Route.post("/v1/auth/login", login, name="login").limited("20/minute"),
            Route.get("/v1/auth/me", me, name="me"),
            Route.post("/v1/auth/refresh", refresh, name="refresh").limited("60/minute"),
        )

        async with self.client(*routes) as client:

            async with database.transaction() as opened:

                await Schema(opened).create(Member.table, member)
                await Schema(opened).create(Grant.table, grant)

            try:

                email    = f"bench-{SUFFIX}@bench.test"
                password = f"Bench-{SUFFIX}-pass"

                await members().create({ "email": email, "password": await thread.offload(crypto.hash, password) })

                login_as = { "email": email, "password": password }
                created  = await client.post("/v1/auth/login", json=login_as)

                self.expect("login", created.code, 200, created.text())

                started = created.json()["data"]
                bearer  = { "Authorization": f"Bearer {started['access_token']}" }
                chain   = [started["refresh_token"]]

                def address () -> dict[str, str]:

                    octets = ".".join(str(rand.number(1, 254)) for _ in range(3))

                    return { "X-Forwarded-For": f"10.{octets}" }

                async def signin () -> None:

                    reply = await client.post("/v1/auth/login", json=login_as, headers=address())

                    self.expect("login", reply.code, 200, reply.text())

                async def read () -> None:

                    reply = await client.get("/v1/auth/me", headers=bearer)

                    self.expect("me", reply.code, 200, reply.text())

                async def rotate () -> None:

                    sent  = { "refresh_token": chain[-1] }
                    reply = await client.post("/v1/auth/refresh", json=sent, headers=address())

                    self.expect("refresh", reply.code, 200, reply.text())
                    chain.append(reply.json()["data"]["refresh_token"])

                latencies, elapsed = await self.measure(read, self.reads, self.concurrency)

                self.report("me", latencies, elapsed, 300.0)

                latencies, elapsed = await self.measure(rotate, self.refreshes, 1)

                self.report("refresh", latencies, elapsed, 300.0)

                latencies, elapsed = await self.measure(signin, self.logins, self.concurrency)

                self.report("login", latencies, elapsed, 2000.0)

            finally:

                async with database.transaction() as cleanup: await Schema(cleanup).drop_all(Grant.table, Member.table)

if __name__ == "__main__":

    asyncio.run(AuthBench().run())
