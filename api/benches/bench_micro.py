from core.crypto import Crypto
from core.rand import rand
from core.string import string
from core.token import JwtAdapter, Token
from core.validate import Email, validate
from core.value import value
from benches import Bench

class MicroBench(Bench):

    def run ( self ) -> None:

        crypto = Crypto()
        token  = Token()
        hashed = crypto.hash("bench-password-1")

        token.setup(JwtAdapter("bench-secret-that-is-long-enough-for-hs256", issuer="bench"))
        crypto.setup([crypto.key()])

        issued, _ = token.issue("bench", "access", 900, roles=["client"])
        sealed    = crypto.seal("payload")

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

if __name__ == "__main__":

    MicroBench().run()
