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
