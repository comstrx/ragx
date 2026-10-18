from collections.abc import Iterable
import re, textwrap, unicodedata

SPACES = re.compile(r"\s+")
UNSAFE = re.compile(r"[^a-z0-9]+")
TAGS   = re.compile(r"<[^>]+>")
ANSI   = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PAIR   = 2

class Text:

    def slug ( self, text: str, separator: str = "-" ) -> str:

        plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()

        return UNSAFE.sub(separator, plain).strip(separator)

    def ascii ( self, text: str ) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()

    def collapse ( self, text: str ) -> str:
        return SPACES.sub(" ", text).strip()

    def squish ( self, text: str ) -> str:
        return self.collapse(text)

    def truncate ( self, text: str, limit: int, suffix: str = "…" ) -> str:

        if len(text) <= limit: return text

        return text[: max(limit - len(suffix), 0)].rstrip() + suffix

    def words_limit ( self, text: str, count: int, suffix: str = "…" ) -> str:

        words = text.split()

        if len(words) <= count: return text

        return " ".join(words[:count]) + suffix

    def wrap ( self, text: str, width: int = 80 ) -> str:
        return textwrap.fill(text, width)

    def indent ( self, text: str, spaces: int = 4 ) -> str:
        return textwrap.indent(text, " " * spaces)

    def dedent ( self, text: str ) -> str:
        return textwrap.dedent(text)

    def mask ( self, text: str, keep: int = 4, symbol: str = "*" ) -> str:

        if keep <= 0 or len(text) <= keep: return symbol * len(text)

        return symbol * (len(text) - keep) + text[-keep:]

    def mask_middle ( self, text: str, head: int = 2, tail: int = 2, symbol: str = "*" ) -> str:

        if len(text) <= head + tail: return symbol * len(text)

        return text[:head] + symbol * (len(text) - head - tail) + text[-tail:]

    def pad_left ( self, text: str, width: int, fill: str = " " ) -> str:
        return text.rjust(width, fill)

    def pad_right ( self, text: str, width: int, fill: str = " " ) -> str:
        return text.ljust(width, fill)

    def pad_both ( self, text: str, width: int, fill: str = " " ) -> str:
        return text.center(width, fill)

    def start ( self, text: str, prefix: str ) -> str:
        return text if text.startswith(prefix) else prefix + text

    def finish ( self, text: str, suffix: str ) -> str:
        return text if text.endswith(suffix) else text + suffix

    def chop_start ( self, text: str, prefix: str ) -> str:
        return text.removeprefix(prefix)

    def chop_end ( self, text: str, suffix: str ) -> str:
        return text.removesuffix(suffix)

    def before ( self, text: str, needle: str ) -> str:
        return text.partition(needle)[0] if needle in text else text

    def after ( self, text: str, needle: str ) -> str:
        return text.partition(needle)[2] if needle in text else text

    def before_last ( self, text: str, needle: str ) -> str:
        return text.rpartition(needle)[0] if needle in text else text

    def after_last ( self, text: str, needle: str ) -> str:
        return text.rpartition(needle)[2] if needle in text else text

    def between ( self, text: str, start: str, end: str ) -> str:
        return self.before_last(self.after(text, start), end) if start in text and end in text else ""

    def replace_first ( self, text: str, old: str, new: str ) -> str:
        return text.replace(old, new, 1)

    def replace_last ( self, text: str, old: str, new: str ) -> str:

        head, found, tail = text.rpartition(old)

        return head + new + tail if found else text

    def replace_many ( self, text: str, pairs: dict[str, str] ) -> str:

        for old, new in pairs.items(): text = text.replace(old, new)

        return text

    def remove ( self, text: str, *needles: str ) -> str:
        return self.replace_many(text, dict.fromkeys(needles, ""))

    def strip_html ( self, text: str ) -> str:
        return self.collapse(TAGS.sub(" ", text))

    def strip_ansi ( self, text: str ) -> str:
        return ANSI.sub("", text)

    def reverse ( self, text: str ) -> str:
        return text[::-1]

    def repeat ( self, text: str, times: int, separator: str = "" ) -> str:
        return separator.join([text] * max(times, 0))

    def word_count ( self, text: str ) -> int:
        return len(text.split())

    def lines ( self, text: str ) -> list[str]:
        return text.splitlines()

    def excerpt ( self, text: str, needle: str, radius: int = 40, omission: str = "…" ) -> str:

        index = text.lower().find(needle.lower())

        if index < 0: return self.truncate(text, radius * PAIR, omission)

        start = max(index - radius, 0)
        end   = min(index + len(needle) + radius, len(text))

        return (omission if start else "") + text[start:end].strip() + (omission if end < len(text) else "")

    def join ( self, parts: Iterable[object], separator: str = ", ", final: str | None = None ) -> str:

        items = [str(part) for part in parts if part is not None and str(part) != ""]

        if final is None or len(items) < PAIR: return separator.join(items)

        return separator.join(items[:-1]) + final + items[-1]

    def contains_any ( self, text: str, *needles: str, ignore_case: bool = False ) -> bool:

        haystack = text.lower() if ignore_case else text

        return any((needle.lower() if ignore_case else needle) in haystack for needle in needles)

    def contains_all ( self, text: str, *needles: str, ignore_case: bool = False ) -> bool:

        haystack = text.lower() if ignore_case else text

        return all((needle.lower() if ignore_case else needle) in haystack for needle in needles)
