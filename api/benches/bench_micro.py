from core.crypto import Crypto
from core.event import Event, Events
from core.queue import MemoryDriver, Queue
from core.rand import rand
from core.string import string
from core.token import JwtAdapter, Token
from core.validate import Email, validate
from core.value import value
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

        asyncio.run(self.pipeline())

        for label, work, rounds, p99 in (
            ("uuid7",        rand.uuid,                                                 50_000, 0.02),
            ("otp",          rand.otp,                                                  20_000, 0.03),
            ("value.int",    lambda: value.integer("12345"),                            50_000, 0.02),
            ("slug",         lambda: string.slug("Hello, World! Benchmarks Are Fun"),   20_000, 0.05),
            ("base64",       lambda: string.from_base64(string.to_base64(b"x" * 256)),  20_000, 0.02),
            ("email",        lambda: validate.check(Email, "Bench@Example.com"),         5_000, 0.10),
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
        seen: list[object] = []

        queue.setup(MemoryDriver())
        events.listen(Ping, seen.append)

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

if __name__ == "__main__":

    MicroBench().run()
