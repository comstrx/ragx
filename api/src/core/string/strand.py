from collections.abc import Callable
from typing import Self, SupportsIndex, override

from .case import Case, Template
from .codec import Codec, Regex
from .compare import Compare
from .inflect import Inflect
from .safety import Safety
from .script import Probe, Script
from .text import Text

class Kit(Case, Inflect, Text, Codec, Probe, Template, Compare, Regex, Script, Safety):

    pass

KIT = Kit()

class Strand(str):

    __slots__ = ()

    def slug ( self, separator: str = "-" ) -> Strand:

        return Strand(KIT.slug(self, separator))

    def snake ( self ) -> Strand:

        return Strand(KIT.snake(self))

    def kebab ( self ) -> Strand:

        return Strand(KIT.kebab(self))

    def studly ( self ) -> Strand:

        return Strand(KIT.studly(self))

    def camel ( self ) -> Strand:

        return Strand(KIT.camel(self))

    def headline ( self ) -> Strand:

        return Strand(KIT.headline(self))

    def sentence ( self ) -> Strand:

        return Strand(KIT.sentence(self))

    @override
    def title ( self ) -> Strand:

        return Strand(KIT.title(self))

    @override
    def upper ( self ) -> Strand:

        return Strand(str.upper(self))

    @override
    def lower ( self ) -> Strand:

        return Strand(str.lower(self))

    def trim ( self, chars: str | None = None ) -> Strand:

        return Strand(str.strip(self, chars))

    def squish ( self ) -> Strand:

        return Strand(KIT.squish(self))

    def ascii ( self ) -> Strand:

        return Strand(KIT.ascii(self))

    def arabic ( self, fold: bool = False ) -> Strand:

        return Strand(KIT.arabic(self, fold))

    def latin_digits ( self ) -> Strand:

        return Strand(KIT.latin_digits(self))

    def strip_marks ( self ) -> Strand:

        return Strand(KIT.strip_marks(self))

    def strip_html ( self ) -> Strand:

        return Strand(KIT.strip_html(self))

    def limit ( self, size: int, suffix: str = "…" ) -> Strand:

        return Strand(KIT.truncate(self, size, suffix))

    def words_limit ( self, count: int, suffix: str = "…" ) -> Strand:

        return Strand(KIT.words_limit(self, count, suffix))

    def mask ( self, keep: int = 4, symbol: str = "*" ) -> Strand:

        return Strand(KIT.mask(self, keep, symbol))

    def start ( self, prefix: str ) -> Strand:

        return Strand(KIT.start(self, prefix))

    def finish ( self, suffix: str ) -> Strand:

        return Strand(KIT.finish(self, suffix))

    def append ( self, *parts: str ) -> Strand:

        return Strand(self + "".join(parts))

    def prepend ( self, *parts: str ) -> Strand:

        return Strand("".join(parts) + self)

    def before ( self, needle: str ) -> Strand:

        return Strand(KIT.before(self, needle))

    def after ( self, needle: str ) -> Strand:

        return Strand(KIT.after(self, needle))

    def between ( self, start: str, end: str ) -> Strand:

        return Strand(KIT.between(self, start, end))

    @override
    def replace ( self, old: str, new: str, count: SupportsIndex = -1 ) -> Strand:

        return Strand(str.replace(self, old, new, count))

    def replace_first ( self, old: str, new: str ) -> Strand:

        return Strand(KIT.replace_first(self, old, new))

    def replace_last ( self, old: str, new: str ) -> Strand:

        return Strand(KIT.replace_last(self, old, new))

    def remove ( self, *needles: str ) -> Strand:

        return Strand(KIT.remove(self, *needles))

    def plural ( self, count: int = 2 ) -> Strand:

        return Strand(KIT.plural(self, count))

    def singular ( self ) -> Strand:

        return Strand(KIT.singular(self))

    def reverse ( self ) -> Strand:

        return Strand(self[::-1])

    def repeat ( self, times: int, separator: str = "" ) -> Strand:

        return Strand(KIT.repeat(self, times, separator))

    def pad_left ( self, width: int, fill: str = " " ) -> Strand:

        return Strand(KIT.pad_left(self, width, fill))

    def pad_right ( self, width: int, fill: str = " " ) -> Strand:

        return Strand(KIT.pad_right(self, width, fill))

    def surround ( self, before: str, after: str | None = None ) -> Strand:

        return Strand(KIT.surround(self, before, after))

    def unwrap ( self, before: str, after: str | None = None ) -> Strand:

        return Strand(KIT.unwrap(self, before, after))

    def fill ( self, **data: object ) -> Strand:

        return Strand(KIT.fill(self, data))

    def pipe ( self, step: Callable[[str], str] ) -> Strand:

        return Strand(step(self))

    def when (
        self, condition: object, step: Callable[[Strand], str], otherwise: Callable[[Strand], str] | None = None,
    ) -> Strand:

        if condition: return Strand(step(self))

        return Strand(otherwise(self)) if otherwise else self

    def unless ( self, condition: object, step: Callable[[Strand], str] ) -> Strand:

        return self.when(not condition, step)

    def tap ( self, look: Callable[[Strand], object] ) -> Self:

        look(self)

        return self

    def explode ( self, separator: str, limit: int = -1 ) -> list[str]:

        return self.split(separator, limit)

    def words ( self ) -> list[str]:

        return str.split(self)

    def is_empty ( self ) -> bool:

        return not self.strip()

    def value ( self ) -> str:

        return str.__str__(self)

class String(Kit):

    def of ( self, value: object ) -> Strand:

        if value is None: return Strand()
        if isinstance(value, bytes | bytearray): return Strand(bytes(value).decode(errors="replace"))

        return Strand(value)

    def is_empty ( self, value: object ) -> bool:

        return self.of(value).strip() == ""

    def limit ( self, text: str, limit: int, suffix: str = "…" ) -> str:

        return self.truncate(text, limit, suffix)

    def length ( self, text: str ) -> int:

        return len(text)
