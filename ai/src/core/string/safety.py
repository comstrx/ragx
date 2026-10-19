from dataclasses import dataclass
from typing import Literal
from core.error import Code, Fault
import phonenumbers, regex, unicodedata

type EntityKind = Literal["email", "phone", "url"]

EMAIL = regex.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^\x60{|}~-]+@[\w-]+(?:\.[\w-]+)+", regex.I)
URL = regex.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\x22]+")
INJECTION = regex.compile(
    r"(?i)(?:ignore|disregard|override)\s+(?:all\s+)?(?:previous|prior|system|developer)\s+"
    r"(?:instructions?|rules?|prompts?)|(?:reveal|print|show)\s+(?:the\s+)?system\s+prompt|"
    r"تجاهل\s+(?:كل\s+)?(?:التعليمات|القواعد)\s*(?:السابقة)?|"
    r"<\|(?:im_start|system|endoftext)\|>|\[INST\]",
)

@dataclass(frozen=True, slots=True)
class Entity:

    kind  : EntityKind
    start : int
    end   : int

@dataclass(frozen=True, slots=True)
class Inspection:

    text       : str
    entities   : tuple[Entity, ...]
    suspicious : bool

class Safety:

    def normalize ( self, text: str ) -> str:

        return "".join(c for c in unicodedata.normalize("NFKC", text) if unicodedata.category(c) != "Cf")

    def inspect ( self, text: str, region: str = "EG", limit: int = 200_000 ) -> Inspection:

        if len(text) > limit: raise Fault(Code.VALIDATION, reason="string.input.limit")

        entities: list[Entity] = []

        patterns: tuple[tuple[EntityKind, regex.Pattern[str]], ...] = (("email", EMAIL), ("url", URL))

        for kind, pattern in patterns:
            entities.extend(Entity(kind, m.start(), m.end()) for m in pattern.finditer(text, timeout=0.1))

        entities.extend(
            Entity("phone", m.start, m.end) for m in phonenumbers.PhoneNumberMatcher(text, region, max_tries=100)
        )
        ordered = sorted(entities, key=lambda item: (item.start, -item.end))
        kept: list[Entity] = []

        for item in ordered:
            if not kept or item.start >= kept[-1].end: kept.append(item)

        suspicious = INJECTION.search(self.normalize(text), timeout=0.1) is not None

        return Inspection(text, tuple(kept), suspicious)

    def redact ( self, text: str, kinds: tuple[EntityKind, ...] = ("email", "phone", "url") ) -> str:

        report = self.inspect(text)

        for entity in reversed(report.entities):
            if entity.kind in kinds:
                text = text[:entity.start] + "[" + entity.kind.upper() + "]" + text[entity.end:]

        return text

    def guard ( self, text: str, reject_injection: bool = False, redact: bool = False ) -> str:

        report = self.inspect(text)

        if reject_injection and report.suspicious: raise Fault(Code.FORBIDDEN, reason="string.injection")

        return self.redact(text) if redact else text
