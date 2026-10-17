from core.rand import rand
from benches import Bench
import asyncio

class AuthBench(Bench):

    logins      = 200
    reads       = 3000
    refreshes   = 300
    concurrency = 8

    async def run ( self ) -> None:

        async with self.client() as client:

            tag      = rand.hex(4)
            email    = f"bench-{tag}@bench.test"
            password = f"Bench-{tag}-pass"
            login_as = { "email": email, "password": password }
            signup   = { "name": f"Bench {tag}", **login_as }
            created  = await client.post("/v1/auth/register", json=signup)

            self.expect("register", created.status_code, 201, created.text)

            session = created.json()["data"]
            bearer  = { "Authorization": f"Bearer {session['access_token']}" }
            chain   = [session["refresh_token"]]

            def address () -> dict[str, str]:
                return { "X-Forwarded-For": f"10.{rand.number(1, 254)}.{rand.number(1, 254)}.{rand.number(1, 254)}" }

            async def login () -> None:

                reply = await client.post("/v1/auth/login", json=login_as, headers=address())

                self.expect("login", reply.status_code, 200, reply.text)

            async def me () -> None:

                reply = await client.get("/v1/auth/me", headers=bearer)

                self.expect("me", reply.status_code, 200, reply.text)

            async def refresh () -> None:

                reply = await client.post("/v1/auth/refresh", json={ "refresh_token": chain[-1] }, headers=address())

                self.expect("refresh", reply.status_code, 200, reply.text)
                chain.append(reply.json()["data"]["refresh_token"])

            latencies, elapsed = await self.measure(me, self.reads, self.concurrency)

            self.report("me", latencies, elapsed, 300.0)

            latencies, elapsed = await self.measure(refresh, self.refreshes, 1)

            self.report("refresh", latencies, elapsed, 300.0)

            latencies, elapsed = await self.measure(login, self.logins, self.concurrency)

            self.report("login", latencies, elapsed, 2000.0)

if __name__ == "__main__":

    asyncio.run(AuthBench().run())
