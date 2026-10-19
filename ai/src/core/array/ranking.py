from collections.abc import Sequence
from dataclasses import dataclass
from core.error import Code, Fault
import math

@dataclass(frozen=True, slots=True)
class Ranked:

    key   : str
    score : float

@dataclass(frozen=True, slots=True)
class RetrievalMetrics:

    recall : float
    mrr    : float
    ndcg   : float

class Ranking:

    def fuse ( self, *rankings: Sequence[Ranked], constant: int = 60 ) -> tuple[Ranked, ...]:

        if constant < 1: raise Fault(Code.VALIDATION, reason="ranking.constant")

        scores: dict[str, float] = {}

        for ranking in rankings:
            seen: set[str] = set()
            for position, item in enumerate(ranking, 1):
                if item.key in seen: raise Fault(Code.VALIDATION, reason="ranking.duplicate")
                seen.add(item.key)
                scores[item.key] = scores.get(item.key, 0) + 1 / (constant + position)

        return tuple(Ranked(key, value) for key, value in sorted(scores.items(), key=lambda row: (-row[1], row[0])))

    def metrics ( self, retrieved: Sequence[str], relevant: frozenset[str], limit: int = 10 ) -> RetrievalMetrics:

        if not relevant or limit < 1 or len(set(retrieved)) != len(retrieved):
            raise Fault(Code.VALIDATION, reason="ranking.metrics.input")

        hits = [position for position, key in enumerate(retrieved[:limit], 1) if key in relevant]
        ideal = math.fsum(1 / math.log2(position + 1) for position in range(1, min(len(relevant), limit) + 1))
        actual = math.fsum(1 / math.log2(position + 1) for position in hits)

        return RetrievalMetrics(len(hits) / len(relevant), 1 / hits[0] if hits else 0.0, actual / ideal)
