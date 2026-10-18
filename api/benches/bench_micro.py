from core.cache import Cache
from core.crypto import Crypto
from core.date import UTC, DateTime
from core.event import Event, Events
from core.http import Route, Router
from core.queue import MemoryDriver, Queue
from core.rand import rand
from core.schedule import Cron
from core.socket import Frame
from core.string import string
from core.token import JwtAdapter, Token
from core.validate import Email, validate
from core.parse import parse
from benches import Bench
import asyncio

class Ping(Event):

    pass

class MicroBench(Bench):

    def run ( self ) -> None:

        self.quiet()

        crypto = Crypto()
        token  = Token()
        hashed = crypto.hash("bench-password-1")

        token.setup(JwtAdapter("bench-secret-that-is-long-enough-for-hs256", issuer="bench"))
        crypto.setup([crypto.key()])

        issued, _ = token.issue("bench", "access", 900, roles=["client"])
        sealed    = crypto.seal("payload")
        router    = Router()
        cron      = Cron("*/15 2 * * 1-5")
        moment    = DateTime(2026, 10, 16, 2, 20, tzinfo=UTC)
        frame     = Frame("headline", "news", { "n": 1 }).encode()

        router.register(Route.group("/v1", [Route.get("/items/{key}", self.pipeline, name="show")], name="v1"))

        asyncio.run(self.pipeline())

        for label, work, rounds, p99 in (
            ("uuid7",        rand.uuid,                                                 50_000, 0.02),
            ("otp",          rand.otp,                                                  20_000, 0.03),
            ("value.int",    lambda: parse.integer("12345"),                            50_000, 0.02),
            ("slug",         lambda: string.slug("Hello, World! Benchmarks Are Fun"),   20_000, 0.05),
            ("base64",       lambda: string.from_base64(string.to_base64(b"x" * 256)),  20_000, 0.02),
            ("email",        lambda: validate.check(Email, "Bench@Example.com"),         5_000, 0.10),
            ("route.url",    lambda: router.url("v1.show", key=7, page=2),              50_000, 0.02),
            ("cron.next",    lambda: cron.next(moment),                                 20_000, 0.10),
            ("frame.decode", lambda: Frame.decode(frame),                               50_000, 0.02),
            ("jwt.issue",    lambda: token.issue("bench", "access", 900),               5_000, 0.30),
            ("jwt.verify",   lambda: token.verify(issued, kind="access"),               5_000, 0.30),
            ("seal.open",    lambda: crypto.open_text(sealed),                          5_000, 0.20),
            ("argon2.hash",  lambda: crypto.hash("bench-password-1"),                      20, 400.0),
            ("argon2.check", lambda: crypto.verify("bench-password-1", hashed),             20, 400.0),
        ):

            latencies, elapsed = self.measure_sync(work, rounds)

            self.report(label, latencies, elapsed, p99)

    async def pipeline ( self ) -> None:

        queue  = Queue()
        events = Events()
        cache  = Cache()
        seen: list[object] = []

        queue.setup(MemoryDriver())
        events.listen(Ping, seen.append)

        async def cached () -> None:

            await cache.set("k", { "n": 1 }, ttl=60)
            await cache.get("k")

        async def noop ( value: int ) -> None:
            seen.append(value)

        async def roundtrip () -> None:

            await queue.push(noop, 1)
            await queue.drain()

        async def dispatch () -> None:
            await events.dispatch(Ping())

        latencies, elapsed = await self.measure(roundtrip, 5000, 1)

        self.report("queue.push+run", latencies, elapsed, 0.5)

        latencies, elapsed = await self.measure(dispatch, 20000, 1)

        self.report("event.dispatch", latencies, elapsed, 0.2)

        latencies, elapsed = await self.measure(cached, 20000, 1)

        self.report("cache.set+get", latencies, elapsed, 0.1)

if __name__ == "__main__":

    MicroBench().run()
