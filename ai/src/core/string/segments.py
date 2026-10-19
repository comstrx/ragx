from dataclasses import dataclass
from core.error import Code, Fault
import regex

@dataclass(frozen=True, slots=True)
class Segment:

    text  : str
    start : int
    end   : int

class Segments:

    def chunks ( self, text: str, size: int = 1200, overlap: int = 120 ) -> tuple[Segment, ...]:

        if size < 1 or overlap < 0 or overlap >= size: raise Fault(Code.VALIDATION, reason="string.chunk.options")

        found: list[Segment] = []
        start = 0

        while start < len(text):
            end = min(start + size, len(text))
            found.append(Segment(text[start:end], start, end))
            if end == len(text): break
            start = end - overlap

        return tuple(found)

    def terms ( self, text: str ) -> tuple[str, ...]:

        return tuple(regex.findall(r"[\p{L}\p{N}]+", text.casefold(), timeout=0.1))
