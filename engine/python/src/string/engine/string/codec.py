from collections.abc import Callable

from engine.error import Code, Fault
import base64, binascii, hashlib, re, secrets, string

ALPHABET = string.ascii_letters + string.digits
BASE64   = "string.base64"
HEX      = "string.hex"
SYMBOLS = re.compile(r"[^\w\s]", re.UNICODE)
SMALL   = ("a", "an", "the", "of", "and", "or", "in", "on")

class Codec:

    def to_base64 ( self, data: str | bytes, url: bool = False ) -> str:

        raw = data.encode() if isinstance(data, str) else data

        return (base64.urlsafe_b64encode(raw) if url else base64.b64encode(raw)).decode()

    def from_base64 ( self, text: str, url: bool = False ) -> bytes:

        padded = text + "=" * (-len(text) % 4)

        try: return base64.urlsafe_b64decode(padded) if url else base64.b64decode(padded, validate=True)
        except (ValueError, binascii.Error) as error: raise Fault(Code.BAD_REQUEST, reason=BASE64) from error

    def to_hex ( self, data: str | bytes ) -> str:

        return (data.encode() if isinstance(data, str) else data).hex()

    def from_hex ( self, text: str ) -> bytes:

        try: return bytes.fromhex(text)
        except ValueError as error: raise Fault(Code.BAD_REQUEST, reason=HEX) from error

    def to_bytes ( self, text: str, encoding: str = "utf-8" ) -> bytes:

        return text.encode(encoding)

    def from_bytes ( self, data: bytes, encoding: str = "utf-8" ) -> str:

        return data.decode(encoding, errors="replace")

    def random ( self, size: int = 16, alphabet: str = ALPHABET ) -> str:

        return "".join(secrets.choice(alphabet) for _ in range(size))

    def token ( self, size: int = 32 ) -> str:

        return secrets.token_urlsafe(size)

    def escape_html ( self, text: str ) -> str:

        return (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;")
        )

    def quote ( self, text: str, mark: str = '"' ) -> str:

        return f"{mark}{text}{mark}"

    def unquote ( self, text: str ) -> str:

        if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'": return text[1:-1]

        return text

class Regex:

    def pattern ( self, expression: str | re.Pattern[str], flags: int = 0 ) -> re.Pattern[str]:

        return expression if isinstance(expression, re.Pattern) else re.compile(expression, flags)

    def match ( self, text: str, expression: str | re.Pattern[str], flags: int = 0 ) -> re.Match[str] | None:

        return self.pattern(expression, flags).match(text)

    def fullmatch ( self, text: str, expression: str | re.Pattern[str], flags: int = 0 ) -> bool:

        return self.pattern(expression, flags).fullmatch(text) is not None

    def search ( self, text: str, expression: str | re.Pattern[str], flags: int = 0 ) -> str | None:

        found = self.pattern(expression, flags).search(text)

        return found.group(0) if found else None

    def groups ( self, text: str, expression: str | re.Pattern[str], flags: int = 0 ) -> dict[str, str]:

        found = self.pattern(expression, flags).search(text)

        return { key: value for key, value in found.groupdict().items() if value is not None } if found else {}

    def sub (
        self, text: str, expression: str | re.Pattern[str], replacement: str | Callable[[re.Match[str]], str],
        count: int = 0, flags: int = 0,
    ) -> str:

        return self.pattern(expression, flags).sub(replacement, text, count=count)

    def split_regex ( self, text: str, expression: str | re.Pattern[str], limit: int = 0 ) -> list[str]:

        return [part for part in self.pattern(expression).split(text, maxsplit=limit) if part != ""]

    def escape ( self, text: str ) -> str:

        return re.escape(text)

    def equals_ignore_case ( self, left: str, right: str ) -> bool:

        return left.casefold() == right.casefold()

    def replace_insensitive ( self, text: str, old: str, new: str, count: int = 0 ) -> str:

        return re.sub(re.escape(old), lambda _: new, text, count=count, flags=re.IGNORECASE)

    def strip_symbols ( self, text: str ) -> str:

        return SYMBOLS.sub("", text)

    def char_count ( self, text: str, spaces: bool = True ) -> int:

        return len(text) if spaces else len("".join(text.split()))

    def hash ( self, text: str, algorithm: str = "sha256", size: int | None = None ) -> str:

        digest = hashlib.new(algorithm, text.encode()).hexdigest()

        return digest[:size] if size else digest

    def title_safe ( self, text: str, small: tuple[str, ...] = SMALL ) -> str:

        words = text.split()

        return " ".join(
            word if word.isupper() else word.lower() if word.lower() in small and index else word.capitalize()
            for index, word in enumerate(words)
        )

    def preserve_case ( self, source: str, replacement: str ) -> str:

        if source.isupper(): return replacement.upper()
        if source[:1].isupper(): return replacement[:1].upper() + replacement[1:]

        return replacement
