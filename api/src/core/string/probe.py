import re

EMAIL  = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL    = re.compile(r"^https?://[^\s/?#]+[^\s]*$")
SLUG   = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UUID   = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PHONE  = re.compile(r"^\+[1-9]\d{6,14}$")
DIGITS = re.compile(r"^\d+$")
WILD   = re.compile(r"[*?]")

class Probe:

    def is_email ( self, text: str ) -> bool:
        return EMAIL.match(text) is not None

    def is_url ( self, text: str ) -> bool:
        return URL.match(text) is not None

    def is_slug ( self, text: str ) -> bool:
        return SLUG.match(text) is not None

    def is_uuid ( self, text: str ) -> bool:
        return UUID.match(text) is not None

    def is_phone ( self, text: str ) -> bool:
        return PHONE.match(text) is not None

    def is_digits ( self, text: str ) -> bool:
        return DIGITS.match(text) is not None

    def is_blank ( self, text: str | None ) -> bool:
        return text is None or text.strip() == ""

    def is_ascii ( self, text: str ) -> bool:
        return text.isascii()

    def matches ( self, text: str, pattern: str, ignore_case: bool = False ) -> bool:
        return re.fullmatch(pattern, text, re.IGNORECASE if ignore_case else 0) is not None

    def has ( self, text: str, pattern: str, ignore_case: bool = False ) -> bool:
        return re.search(pattern, text, re.IGNORECASE if ignore_case else 0) is not None

    def like ( self, text: str, glob: str, ignore_case: bool = True ) -> bool:

        regex = "".join(".*" if char == "*" else "." if char == "?" else re.escape(char) for char in glob)

        return re.fullmatch(regex, text, re.IGNORECASE if ignore_case else 0) is not None

    def is_glob ( self, text: str ) -> bool:
        return WILD.search(text) is not None

    def count ( self, text: str, needle: str, ignore_case: bool = False ) -> int:
        return (text.lower() if ignore_case else text).count(needle.lower() if ignore_case else needle)

    def find_all ( self, text: str, pattern: str ) -> list[str]:
        return re.findall(pattern, text)

    def equals ( self, left: str, right: str, ignore_case: bool = True ) -> bool:
        return left.casefold() == right.casefold() if ignore_case else left == right

    def starts_any ( self, text: str, *prefixes: str ) -> bool:
        return text.startswith(prefixes)

    def ends_any ( self, text: str, *suffixes: str ) -> bool:
        return text.endswith(suffixes)
