from collections.abc import Iterable
import hashlib, re, secrets, string, unicodedata

WORDS      = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z0-9]+|[A-Z]+|\d+")
SPACES     = re.compile(r"\s+")
UNSAFE     = re.compile(r"[^a-z0-9]+")
EMAIL      = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL        = re.compile(r"^https?://[^\s/?#]+[^\s]*$")
ALPHABET   = string.ascii_letters + string.digits
HASHES     = ("sha256", "sha512", "blake2b")
PAIR       = 2


class String:

    def words ( self, text: str ) -> list[str]:
        return [word.lower() for word in WORDS.findall(text.replace("_", " ").replace("-", " "))]

    def snake ( self, text: str ) -> str:
        return "_".join(self.words(text))

    def kebab ( self, text: str ) -> str:
        return "-".join(self.words(text))

    def studly ( self, text: str ) -> str:
        return "".join(word.capitalize() for word in self.words(text))

    def camel ( self, text: str ) -> str:

        studly = self.studly(text)

        return studly[:1].lower() + studly[1:]

    def title ( self, text: str ) -> str:
        return " ".join(word.capitalize() for word in self.words(text))

    def slug ( self, text: str, separator: str = "-" ) -> str:

        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()

        return UNSAFE.sub(separator, plain).strip(separator)

    def collapse ( self, text: str ) -> str:
        return SPACES.sub(" ", text).strip()

    def truncate ( self, text: str, limit: int, suffix: str = "…" ) -> str:

        if len(text) <= limit: return text

        return text[: max(limit - len(suffix), 0)].rstrip() + suffix

    def mask ( self, text: str, keep: int = 4, symbol: str = "*" ) -> str:

        if keep <= 0 or len(text) <= keep: return symbol * len(text)

        return symbol * (len(text) - keep) + text[-keep:]

    def random ( self, size: int = 16, alphabet: str = ALPHABET ) -> str:
        return "".join(secrets.choice(alphabet) for _ in range(size))

    def token ( self, size: int = 32 ) -> str:
        return secrets.token_urlsafe(size)

    def hash ( self, text: str, algorithm: str = "sha256" ) -> str:

        if algorithm not in HASHES: raise ValueError(algorithm)

        return hashlib.new(algorithm, text.encode()).hexdigest()

    def join ( self, parts: Iterable[object], separator: str = ", ", final: str | None = None ) -> str:

        items = [str(part) for part in parts if part is not None and str(part) != ""]

        if final is None or len(items) < PAIR: return separator.join(items)

        return separator.join(items[:-1]) + final + items[-1]

    def is_email ( self, text: str ) -> bool:
        return EMAIL.match(text) is not None

    def is_url ( self, text: str ) -> bool:
        return URL.match(text) is not None

    def is_blank ( self, text: str | None ) -> bool:
        return text is None or text.strip() == ""

    def plural ( self, word: str, count: int = 2 ) -> str:

        if count == 1: return word
        if word.endswith(("s", "x", "z", "ch", "sh")): return word + "es"
        if word.endswith("y") and word[-2:-1] not in "aeiou": return word[:-1] + "ies"

        return word + "s"
