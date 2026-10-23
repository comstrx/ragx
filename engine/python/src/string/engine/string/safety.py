from dataclasses import dataclass
from typing import Literal

from engine.error import Code, Fault
from .text import Text
import phonenumbers, re, unicodedata

type Entity = Literal["email", "phone", "url", "card"]

KINDS     : tuple[Entity, ...] = ("email", "phone", "url", "card")
LIMIT     = 200_000
TRIES     = 200
REGION    = "EG"
EMAIL     = re.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
URL       = re.compile(r"\b(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)
CARD      = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
LEADS     = r"(?:ignore|disregard|override|forget|bypass)"
PRIOR     = r"(?:all\s+|any\s+)?(?:the\s+|your\s+)?(?:previous|prior|above|earlier|system|developer)"
ORDERS    = r"(?:instructions?|rules?|prompts?|messages?|guidelines?)"
SHOWN     = r"(?:reveal|print|show|repeat|output|display)\s+(?:me\s+)?(?:the\s+|your\s+)?(?:system|hidden)\s+prompt"
ARABIC    = (
    r"(?:تجاهل|انس|اهمل|تخط)\s+(?:كل\s+|جميع\s+)?(?:التعليمات|القواعد|الاوامر|التوجيهات)",
    r"(?:اكشف|اعرض|اظهر|اطبع)\s+(?:لي\s+)?(?:تعليمات|موجه|اوامر)\s+النظام",
)
MARKERS   = (r"<\|(?:im_start|im_end|system|endoftext)\|>", r"\[/?inst\]", r"<<sys>>")
INJECTION = re.compile("|".join((rf"{LEADS}\s+{PRIOR}\s+{ORDERS}", SHOWN, *ARABIC, *MARKERS)))
CONTROL   = re.compile("|".join(MARKERS), re.IGNORECASE)
FOLDING   = Text()

def luhn ( digits: str ) -> bool:

    total = 0

    for index, char in enumerate(reversed(digits)):

        total += sum(divmod(int(char) * (2 if index % 2 else 1), 10))

    return total % 10 == 0

@dataclass(frozen=True, slots=True)
class Span:

    kind  : Entity
    start : int
    end   : int

@dataclass(frozen=True, slots=True)
class Inspection:

    spans      : tuple[Span, ...]
    suspicious : bool

    def kinds ( self ) -> frozenset[Entity]:

        return frozenset(span.kind for span in self.spans)

class Safety:

    def visible ( self, text: str ) -> str:

        return "".join(char for char in text if unicodedata.category(char) != "Cf")

    def neutralize ( self, text: str ) -> str:

        return CONTROL.sub("", self.visible(text))

    def suspicious ( self, text: str ) -> bool:

        self.bounded(text)

        return INJECTION.search(FOLDING.fold(self.visible(text))) is not None

    def entities ( self, text: str, region: str = REGION ) -> tuple[Span, ...]:

        self.bounded(text)

        found = [Span("email", match.start(), match.end()) for match in EMAIL.finditer(text)]

        found.extend(Span("url", match.start(), match.end()) for match in URL.finditer(text))
        found.extend(
            Span("card", match.start(), match.end())
            for match in CARD.finditer(text) if luhn("".join(char for char in match.group() if char.isdigit()))
        )
        found.extend(
            Span("phone", match.start, match.end)
            for match in phonenumbers.PhoneNumberMatcher(text, region, max_tries=TRIES)
        )

        kept: list[Span] = []

        for span in sorted(found, key=lambda item: (item.start, -item.end)):

            if not kept or span.start >= kept[-1].end: kept.append(span)

        return tuple(kept)

    def inspect ( self, text: str, region: str = REGION ) -> Inspection:

        return Inspection(self.entities(text, region), self.suspicious(text))

    def redact ( self, text: str, kinds: tuple[Entity, ...] = KINDS, region: str = REGION ) -> str:

        result = text

        for span in reversed(self.entities(text, region)):

            if span.kind in kinds: result = f"{result[:span.start]}[{span.kind.upper()}]{result[span.end:]}"

        return result

    def guard ( self, text: str, reject: bool = False, redact: bool = False, region: str = REGION ) -> str:

        if reject and self.suspicious(text): raise Fault(Code.FORBIDDEN, reason="string.injection")

        return self.redact(text, region=region) if redact else text

    def bounded ( self, text: str ) -> None:

        if len(text) > LIMIT: raise Fault(Code.VALIDATION, reason="string.limit")
