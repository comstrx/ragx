import random, secrets

LOREM = (
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit", "sed", "do", "eiusmod", "tempor",
    "incididunt", "ut", "labore", "et", "dolore", "magna", "aliqua", "enim", "ad", "minim", "veniam", "quis", "nostrud",
    "exercitation", "ullamco", "laboris", "nisi", "aliquip", "ex", "ea", "commodo", "consequat",
)
TLDS  = ("test", "example", "invalid", "localhost")
OCTET = 256
HEX   = "0123456789abcdef"

class Fake:

    def __init__ ( self ) -> None:

        self._system = secrets.SystemRandom()

    def engine ( self ) -> random.Random:
        return self._system

    def gaussian ( self, mean: float = 0.0, deviation: float = 1.0 ) -> float:
        return self._system.gauss(mean, deviation)

    def boolean ( self, probability: float = 0.5 ) -> bool:
        return self._system.random() < probability

    def sign ( self ) -> int:
        return 1 if self.boolean() else -1

    def digits ( self, count: int ) -> str:
        return "".join(str(self._system.randrange(10)) for _ in range(max(count, 0)))

    def ipv4 ( self, private: bool = True ) -> str:

        tail = [str(self._system.randrange(OCTET)) for _ in range(2)] + [str(self._system.randrange(1, 255))]

        if private: return ".".join(["10", *tail])

        return ".".join([str(self._system.randrange(1, 255)), *tail])

    def ipv6 ( self ) -> str:
        return ":".join("".join(self._system.choice(HEX) for _ in range(4)) for _ in range(8))

    def mac ( self ) -> str:

        first = self._system.randrange(OCTET) & 0b11111110 | 0b00000010

        return ":".join([f"{first:02x}", *(f"{self._system.randrange(OCTET):02x}" for _ in range(5))])

    def word ( self ) -> str:
        return self._system.choice(LOREM)

    def words ( self, count: int = 3 ) -> list[str]:
        return [self.word() for _ in range(max(count, 0))]

    def sentence ( self, words: int = 8 ) -> str:

        spoken = " ".join(self.words(words))

        return f"{spoken[:1].upper()}{spoken[1:]}." if spoken else ""

    def paragraph ( self, sentences: int = 4, words: int = 8 ) -> str:
        return " ".join(self.sentence(words) for _ in range(max(sentences, 0)))

    def title ( self, words: int = 3 ) -> str:
        return " ".join(word.capitalize() for word in self.words(words))

    def domain ( self, tld: str | None = None ) -> str:
        return f"{self.word()}{self._system.randrange(100, 999)}.{tld or self._system.choice(TLDS)}"

    def email ( self, domain: str | None = None ) -> str:
        return f"{self.word()}.{self.word()}{self._system.randrange(10, 99)}@{domain or self.domain()}"

    def url ( self, scheme: str = "https", domain: str | None = None ) -> str:
        return f"{scheme}://{domain or self.domain()}/{'/'.join(self.words(2))}"

    def phone ( self, prefix: str = "+1555" ) -> str:
        return f"{prefix}{self.digits(7)}"

    def latitude ( self ) -> float:
        return round(self._system.uniform(-90, 90), 6)

    def longitude ( self ) -> float:
        return round(self._system.uniform(-180, 180), 6)

    def amount ( self, low: float = 1.0, high: float = 1000.0, digits: int = 2 ) -> float:
        return round(self._system.uniform(low, high), digits)
