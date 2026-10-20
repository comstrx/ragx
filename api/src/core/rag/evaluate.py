from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from core.array import Metrics
from core.error import Code, Fault
from core.json import Schema, json
from core.llm import Llm, Prompt
from core.string import string
from .contract import Answer, Evaluation, Passage, Policies, Settings

type Predicate = Callable[[Answer], bool]

JUDGE  = (
    "Judge whether the answer is fully supported by the supplied untrusted sources. "
    "Return JSON with score from 0 (unsupported) to 1 (fully supported) and a short reasoning."
)
JUDGED = Schema({
    "type": "object", "additionalProperties": False, "required": ["score", "reasoning"],
    "properties": { "score": { "type": "number", "minimum": 0, "maximum": 1 }, "reasoning": { "type": "string" } },
})

class Answering(Protocol):

    async def ask ( self, question: str, scope: str ) -> Answer: ...

    async def evaluate ( self, question: str, answer: Answer ) -> Evaluation: ...

    def metrics ( self, retrieved: Sequence[Passage], relevant: Iterable[str], limit: int = 10 ) -> Metrics: ...

def judged ( question: str, answer: str, passages: Sequence[Passage] ) -> str:

    sources = [{ "id": passage.id, "content": string.neutralize(passage.text) } for passage in passages]

    return json.dumps({ "question": question, "answer": answer, "untrusted_sources": sources })

def plain ( text: str ) -> str:

    return string.latin_digits(string.fold(text))

def dominant ( text: str ) -> str:

    letters = [string.script_of(char) for char in text if char.isalpha()]

    return max(set(letters), key=letters.count) if letters else "unknown"

@dataclass(frozen=True, slots=True)
class Check:

    name : str
    test : Predicate

    @classmethod
    def contains ( cls, *words: str ) -> Check:

        wanted = [plain(word) for word in words]

        return cls(f"contains:{'|'.join(words)}", lambda answer: any(word in plain(answer.text) for word in wanted))

    @classmethod
    def lacks ( cls, *words: str ) -> Check:

        unwanted = [plain(word) for word in words]

        return cls(f"lacks:{'|'.join(words)}", lambda answer: not any(word in plain(answer.text) for word in unwanted))

    @classmethod
    def script ( cls, name: str ) -> Check:

        return cls(f"script:{name}", lambda answer: dominant(answer.text) == name)

    @classmethod
    def cites ( cls, *documents: str ) -> Check:

        allowed = frozenset(documents)

        def cited ( answer: Answer ) -> bool:

            found = { passage.document for passage in answer.citations }

            return bool(found) and found <= allowed

        return cls(f"cites:{'|'.join(sorted(allowed))}", cited)

    @classmethod
    def when ( cls, name: str, test: Predicate ) -> Check:

        return cls(name, test)

@dataclass(frozen=True, slots=True)
class Case:

    question : str
    relevant : frozenset[str]
    checks   : tuple[Check, ...] = ()

    @classmethod
    def of ( cls, question: str, relevant: Iterable[str], *checks: Check ) -> Case:

        return cls(question, frozenset(relevant), checks)

@dataclass(frozen=True, slots=True)
class Verdict:

    question : str
    answer   : str
    cited    : tuple[str, ...]
    metrics  : Metrics
    checks   : dict[str, bool]
    judged   : float | None
    accepted : bool

    def failed ( self ) -> list[str]:

        return [name for name, passed in self.checks.items() if not passed]

@dataclass(frozen=True, slots=True)
class Report:

    verdicts : tuple[Verdict, ...]
    accepted : bool = field(init=False)

    def __post_init__ ( self ) -> None:

        object.__setattr__(self, "accepted", bool(self.verdicts) and all(item.accepted for item in self.verdicts))

    def require ( self ) -> Report:

        if self.accepted: return self

        failed = { item.question: item.failed() or ["judge"] for item in self.verdicts if not item.accepted }

        raise Fault(Code.VALIDATION, reason="rag.quality", errors=failed)

    def dump ( self ) -> dict[str, Any]:

        return {
            "accepted": self.accepted,
            "cases": [
                {
                    "question": item.question, "answer": item.answer, "cited": list(item.cited),
                    "recall": item.metrics.recall, "mrr": item.metrics.mrr, "ndcg": item.metrics.ndcg,
                    "checks": item.checks, "judged": item.judged, "accepted": item.accepted,
                } for item in self.verdicts
            ],
        }

class Judge:

    def __init__ ( self, brain: Llm, policies: Policies, settings: Settings ) -> None:

        self._llm      = brain
        self._policies = policies
        self._settings = settings

    def judge ( self, provider: str | None = None ) -> Prompt:

        if provider is None and not self._llm.serves("evaluate"):
            raise Fault(Code.INTERNAL, reason="rag.evaluation.missing")

        chosen = self._llm.prompt(provider) if provider is not None else self._llm.task("evaluate")

        return chosen.harness(self._policies.stage("evaluation")).instruct(JUDGE)

    async def evaluate ( self, question: str, answer: Answer, provider: str | None = None ) -> Evaluation:

        asked = judged(question, answer.text, answer.passages)
        reply = await self.judge(provider).schema(JUDGED, self._settings.native).ask(asked)
        data  = reply.payload()

        return Evaluation(float(data["score"]), str(data["reasoning"]), reply.model)

class Quality:

    def __init__ (
        self, rag: Answering, scope: str, limit: int = 3, recall: float = 1.0, floor: float | None = None,
    ) -> None:

        self._rag    = rag
        self._scope  = scope
        self._limit  = limit
        self._recall = recall
        self._floor  = floor

    async def run ( self, cases: Sequence[Case] ) -> Report:

        return Report(tuple([await self.verdict(case) for case in cases]))

    async def verdict ( self, case: Case ) -> Verdict:

        answer  = await self._rag.ask(case.question, self._scope)
        metrics = self._rag.metrics(answer.passages, case.relevant, self._limit)
        named   = { check.name: check.test(answer) for check in case.checks }
        checks  = { "recall": metrics.recall >= self._recall, **named }
        judged  = (await self._rag.evaluate(case.question, answer)).score if self._floor is not None else None
        passed  = all(checks.values()) and (judged is None or self._floor is None or judged >= self._floor)
        cited   = tuple(dict.fromkeys(passage.document for passage in answer.citations))

        return Verdict(case.question, answer.text, cited, metrics, checks, judged, passed)
