from collections.abc import Iterable
import difflib, re

WORDS   = re.compile(r"[A-Za-z0-9]+")
DIGITS  = re.compile(r"\D+")
LETTERS = re.compile(r"[^A-Za-z]+")

class Compare:

    def levenshtein ( self, left: str, right: str ) -> int:

        if left == right: return 0
        if not left or not right: return len(left or right)

        previous = list(range(len(right) + 1))

        for row, char in enumerate(left, start=1):

            current = [row]

            for column, other in enumerate(right, start=1):

                cost = previous[column - 1] + (char != other)

                current.append(min(previous[column] + 1, current[column - 1] + 1, cost))

            previous = current

        return previous[-1]

    def similarity ( self, left: str, right: str ) -> float:
        return round(difflib.SequenceMatcher(None, left, right).ratio(), 4)

    def closest ( self, text: str, choices: Iterable[str], cutoff: float = 0.6 ) -> str | None:

        found = difflib.get_close_matches(text, list(choices), n=1, cutoff=cutoff)

        return found[0] if found else None

    def common_prefix ( self, *texts: str ) -> str:

        if not texts: return ""

        first = min(texts, key=len)

        for index, char in enumerate(first):
            if any(text[index] != char for text in texts): return first[:index]

        return first

    def common_suffix ( self, *texts: str ) -> str:
        return self.common_prefix(*(text[::-1] for text in texts))[::-1]

    def initials ( self, text: str, limit: int = 2, separator: str = "" ) -> str:
        return separator.join(word[0].upper() for word in WORDS.findall(text)[:limit])

    def acronym ( self, text: str ) -> str:
        return "".join(word[0].upper() for word in WORDS.findall(text))

    def digits ( self, text: str ) -> str:
        return DIGITS.sub("", text)

    def letters ( self, text: str ) -> str:
        return LETTERS.sub("", text)

    def char_at ( self, text: str, index: int, default: str = "" ) -> str:
        return text[index] if -len(text) <= index < len(text) else default

    def position ( self, text: str, needle: str, start: int = 0 ) -> int | None:

        found = text.find(needle, start)

        return found if found >= 0 else None

    def take ( self, text: str, count: int ) -> str:
        return text[:count] if count >= 0 else text[count:]

    def substr ( self, text: str, start: int, length: int | None = None ) -> str:
        return text[start:] if length is None else text[start:start + length]

    def surround ( self, text: str, before: str, after: str | None = None ) -> str:
        return f"{before}{text}{after if after is not None else before}"

    def unwrap ( self, text: str, before: str, after: str | None = None ) -> str:

        tail = after if after is not None else before

        text = text.removeprefix(before)

        if tail: text = text.removesuffix(tail)

        return text

    def is_anagram ( self, left: str, right: str ) -> bool:
        return sorted(left.replace(" ", "").lower()) == sorted(right.replace(" ", "").lower())

    def is_palindrome ( self, text: str ) -> bool:

        plain = "".join(char.lower() for char in text if char.isalnum())

        return plain == plain[::-1]

    def diff ( self, left: str, right: str ) -> list[str]:
        return list(difflib.unified_diff(left.splitlines(), right.splitlines(), lineterm="", n=0))[2:]
