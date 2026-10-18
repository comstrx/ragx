from .case import Case
from .codec import Codec
from .compare import Compare
from .inflect import Inflect
from .probe import Probe
from .regex import Regex
from .template import Template
from .text import Text

class String(Case, Inflect, Text, Codec, Probe, Template, Compare, Regex):

    def of ( self, value: object ) -> str:

        if value is None: return ""
        if isinstance(value, bytes | bytearray): return bytes(value).decode(errors="replace")

        return str(value)

    def is_empty ( self, value: object ) -> bool:
        return self.of(value).strip() == ""

    def limit ( self, text: str, limit: int, suffix: str = "…" ) -> str:
        return self.truncate(text, limit, suffix)

    def length ( self, text: str ) -> int:
        return len(text)
