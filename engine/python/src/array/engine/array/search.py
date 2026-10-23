from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from engine.error import Code, Fault
from engine.number import Embedding, Vector
from engine.string import Text
import heapq, math

FUSION     = 60
SATURATION = 1.2
LENGTHS    = 0.75
VECTORS    = Vector()
WORDS      = Text()

@dataclass(frozen=True, slots=True)
class Ranked:

    key   : str
    score : float

@dataclass(frozen=True, slots=True)
class Metrics:

    recall : float
    mrr    : float
    ndcg   : float

@dataclass(frozen=True, slots=True)
class Item:

    key       : str
    scope     : str
    text      : str
    embedding : Embedding

@dataclass(frozen=True, slots=True)
class Entry:

    item   : Item
    unit   : Embedding
    terms  : Counter[str]
    length : int

class Ranking:

    def fuse ( self, *rankings: Sequence[Ranked], constant: int = FUSION ) -> tuple[Ranked, ...]:

        if constant < 1: raise Fault(Code.VALIDATION, reason="ranking.constant")

        scores: dict[str, float] = {}

        for ranking in rankings:

            keys = [item.key for item in ranking]

            if len(set(keys)) != len(keys): raise Fault(Code.VALIDATION, reason="ranking.duplicate")

            for position, key in enumerate(keys, 1): scores[key] = scores.get(key, 0.0) + 1 / (constant + position)

        return tuple(Ranked(key, value) for key, value in sorted(scores.items(), key=lambda row: (-row[1], row[0])))

    def metrics ( self, retrieved: Sequence[str], relevant: Iterable[str], limit: int = 10 ) -> Metrics:

        wanted = frozenset(relevant)

        if not wanted or limit < 1 or len(set(retrieved)) != len(retrieved):
            raise Fault(Code.VALIDATION, reason="ranking.metrics")

        hits   = [position for position, key in enumerate(retrieved[:limit], 1) if key in wanted]
        ideal  = math.fsum(1 / math.log2(position + 1) for position in range(1, min(len(wanted), limit) + 1))
        actual = math.fsum(1 / math.log2(position + 1) for position in hits)

        return Metrics(len(hits) / len(wanted), 1 / hits[0] if hits else 0.0, actual / ideal)

class Search:

    def __init__ ( self, capacity: int = 10_000 ) -> None:

        self.capacity = capacity
        self._scopes: dict[str, dict[str, Entry]] = {}
        self._owners: dict[str, str] = {}
        self._dimension: int | None = None

    def dimension ( self ) -> int | None:

        return self._dimension

    def count ( self, scope: str | None = None ) -> int:

        return len(self._owners) if scope is None else len(self._scopes.get(scope, {}))

    def upsert ( self, items: Iterable[Item], remove: Iterable[str] = () ) -> None:

        scopes    = dict(self._scopes)
        owners    = dict(self._owners)
        dimension = self._dimension if self._owners else None

        for key in remove:

            owner = owners.pop(key, None)

            if owner is not None: scopes[owner] = self.without(scopes[owner], key)

        for item in items:

            if not item.key or not item.scope: raise Fault(Code.VALIDATION, reason="search.key")
            if owners.get(item.key, item.scope) != item.scope: raise Fault(Code.CONFLICT, reason="search.scope")

            unit      = VECTORS.unit(VECTORS.of(item.embedding, dimension))
            dimension = len(unit)
            terms     = Counter(WORDS.terms(item.text))
            scopes[item.scope] = { **scopes.get(item.scope, {}), item.key: Entry(item, unit, terms, terms.total()) }
            owners[item.key]   = item.scope

        if len(owners) > self.capacity: raise Fault(Code.VALIDATION, reason="search.capacity")

        self._scopes    = { scope: entries for scope, entries in scopes.items() if entries }
        self._owners    = owners
        self._dimension = dimension if owners else None

    def items ( self, scope: str ) -> tuple[Item, ...]:

        return tuple(entry.item for entry in self.entries(scope))

    def entries ( self, scope: str ) -> tuple[Entry, ...]:

        if not scope: raise Fault(Code.FORBIDDEN, reason="search.scope")

        return tuple(self._scopes.get(scope, {}).values())

    def dense ( self, embedding: Sequence[float], scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        self.bounded(limit)

        entries = self.entries(scope)

        if not entries: return ()

        query  = VECTORS.unit(VECTORS.of(embedding, self._dimension))
        scored = (Ranked(entry.item.key, math.sumprod(query, entry.unit)) for entry in entries)

        return tuple(heapq.nsmallest(limit, scored, key=self.order))

    def lexical ( self, query: str, scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        self.bounded(limit)

        entries = self.entries(scope)
        terms   = set(WORDS.terms(query))

        if not entries or not terms: return ()

        average = math.fsum(entry.length for entry in entries) / len(entries) or 1.0
        counts  = { term: sum(term in entry.terms for entry in entries) for term in terms }
        weights = { term: math.log(1 + (len(entries) - found + 0.5) / (found + 0.5)) for term, found in counts.items() }
        scored  = [Ranked(entry.item.key, self.bm25(entry, weights, average)) for entry in entries]

        return tuple(heapq.nsmallest(limit, (item for item in scored if item.score > 0), key=self.order))

    def bm25 ( self, entry: Entry, weights: dict[str, float], average: float ) -> float:

        scale = SATURATION * (1 - LENGTHS + LENGTHS * entry.length / average)

        return math.fsum(
            weight * found * (SATURATION + 1) / (found + scale)
            for term, weight in weights.items() if (found := entry.terms[term])
        )

    def hybrid ( self, query: str, embedding: Sequence[float], scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        return Ranking().fuse(self.dense(embedding, scope, limit), self.lexical(query, scope, limit))[:limit]

    def clear ( self, scope: str ) -> int:

        keys = [entry.item.key for entry in self.entries(scope)]

        self.upsert((), keys)

        return len(keys)

    def without ( self, entries: dict[str, Entry], key: str ) -> dict[str, Entry]:

        return { name: entry for name, entry in entries.items() if name != key }

    def bounded ( self, limit: int ) -> None:

        if limit < 1: raise Fault(Code.VALIDATION, reason="search.limit")

    def order ( self, item: Ranked ) -> tuple[float, str]:

        return -item.score, item.key
