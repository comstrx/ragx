from typing import Literal

import re, unicodedata

type Form = Literal["NFC", "NFD", "NFKC", "NFKD"]

TATWEEL  = "ـ"
ALEFS    = str.maketrans({ "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا" })
FOLDS    = str.maketrans({ "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي" })
EASTERN  = "٠١٢٣٤٥٦٧٨٩"
PERSIAN  = "۰۱۲۳۴۵۶۷۸۹"
LATIN    = "0123456789"
TO_LATIN = str.maketrans(EASTERN + PERSIAN, LATIN + LATIN)
TO_ARAB  = str.maketrans(LATIN, EASTERN)
RIGHT    = frozenset({"R", "AL"})
LEFT     = frozenset({"L"})
UPPERS   = re.compile(r"(?<!^)(?=[A-Z])")
ARABIC   = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
EMAIL  = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL    = re.compile(r"^https?://[^\s/?#]+[^\s]*$")
SLUG   = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
UUID   = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
PHONE  = re.compile(r"^\+[1-9]\d{6,14}$")
DIGITS = re.compile(r"^\d+$")
WILD   = re.compile(r"[*?]")

class Script:

    def normalize ( self, text: str, form: Form = "NFKC" ) -> str:

        return unicodedata.normalize(form, text)

    def strip_marks ( self, text: str ) -> str:

        decomposed = unicodedata.normalize("NFD", text)
        kept       = "".join(char for char in decomposed if not unicodedata.category(char).startswith("M"))

        return unicodedata.normalize("NFC", kept).replace(TATWEEL, "")

    def arabic ( self, text: str, fold: bool = False ) -> str:

        plain = self.strip_marks(unicodedata.normalize("NFKC", text)).translate(ALEFS)

        return plain.translate(FOLDS) if fold else plain

    def has_arabic ( self, text: str ) -> bool:

        return ARABIC.search(text) is not None

    def is_rtl ( self, text: str ) -> bool:

        return any(unicodedata.bidirectional(char) in RIGHT for char in text)

    def direction ( self, text: str ) -> str:

        for char in text:

            kind = unicodedata.bidirectional(char)

            if kind in RIGHT: return "rtl"
            if kind in LEFT: return "ltr"

        return "neutral"

    def latin_digits ( self, text: str ) -> str:

        return text.translate(TO_LATIN)

    def arabic_digits ( self, text: str ) -> str:

        return text.translate(TO_ARAB)

    def deduplicate ( self, text: str, char: str = " " ) -> str:

        return re.sub(f"(?:{re.escape(char)})+", char, text) if char else text

    def ucsplit ( self, text: str ) -> list[str]:

        return [part for part in UPPERS.split(text) if part]

    def graphemes ( self, text: str ) -> list[str]:

        clusters: list[str] = []

        for char in unicodedata.normalize("NFC", text):

            if clusters and unicodedata.combining(char): clusters[-1] += char
            else: clusters.append(char)

        return clusters

    def visible_length ( self, text: str ) -> int:

        return len(self.graphemes(text))

    def control_free ( self, text: str, keep: str = "\n\t" ) -> str:

        return "".join(char for char in text if char in keep or not unicodedata.category(char).startswith("C"))

    def bidi_safe ( self, text: str ) -> str:

        return "".join(char for char in text if unicodedata.category(char) != "Cf" or char in "‌‍")

    def is_printable ( self, text: str ) -> bool:

        return all(char.isprintable() or char in "\n\t" for char in text)

    def script_of ( self, char: str ) -> str:

        name = unicodedata.name(char, "")

        return name.split(" ")[0].lower() if name else "unknown"

    def scripts ( self, text: str ) -> list[str]:

        found = { self.script_of(char) for char in text if char.isalpha() }

        return sorted(found)

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
