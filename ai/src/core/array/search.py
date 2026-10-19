from collections.abc import Sequence
from dataclasses import dataclass
from core.error import Code, Fault
from core.number import UnitVector, vector
from core.string import segments
from .ranking import Ranked, Ranking
import math

@dataclass(frozen=True, slots=True)
class SearchItem:

    key       : str
    scope     : str
    text      : str
    embedding : tuple[float, ...]

class Search:

    def __init__ ( self, identity: str, capacity: int = 10_000 ) -> None:

        self.identity = identity
        self.capacity = capacity
        self._items: dict[str, SearchItem] = {}
        self._vectors: dict[str, UnitVector] = {}
        self._dimension: int | None = None

    def upsert ( self, items: Sequence[SearchItem], remove: frozenset[str] = frozenset() ) -> None:

        draft = {key: item for key, item in self._items.items() if key not in remove}
        normalized = {key: value for key, value in self._vectors.items() if key not in remove}
        dimension = self._dimension

        for item in items:
            if not item.scope or not item.key: raise Fault(Code.VALIDATION, reason="search.identity")
            vector.validate(item.embedding, dimension)
            dimension = len(item.embedding)
            previous = draft.get(item.key)
            if previous is not None and previous.scope != item.scope:
                raise Fault(Code.CONFLICT, reason="search.scope")
            draft[item.key] = item
            normalized[item.key] = UnitVector(item.embedding)

        if len(draft) > self.capacity: raise Fault(Code.VALIDATION, reason="search.capacity")

        self._items, self._dimension, self._vectors = draft, dimension, normalized

    def items ( self, scope: str ) -> tuple[SearchItem, ...]:

        if not scope: raise Fault(Code.FORBIDDEN, reason="search.scope")
        return tuple(item for item in self._items.values() if item.scope == scope)

    def dense ( self, embedding: Sequence[float], scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        if limit < 1: raise Fault(Code.VALIDATION, reason="search.limit")
        vector.validate(embedding, self._dimension)
        query = UnitVector(tuple(embedding))
        scored = [Ranked(item.key, query.cosine(self._vectors[item.key])) for item in self.items(scope)]
        return tuple(sorted(scored, key=lambda item: (-item.score, item.key))[:limit])

    def lexical ( self, query: str, scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        items = self.items(scope)
        if not items: return ()
        terms = set(segments.terms(query))
        documents = [segments.terms(item.text) for item in items]
        mean = sum(map(len, documents)) / len(documents) or 1
        frequencies = {term: sum(term in document for document in documents) for term in terms}
        scores: list[Ranked] = []

        for item, words in zip(items, documents, strict=True):
            score = 0.0
            for term in terms:
                count = words.count(term)
                frequency = frequencies[term]
                inverse = math.log(1 + (len(items) - frequency + 0.5) / (frequency + 0.5))
                score += inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(words) / mean))
            if score: scores.append(Ranked(item.key, score))

        return tuple(sorted(scores, key=lambda item: (-item.score, item.key))[:limit])

    def hybrid ( self, query: str, embedding: Sequence[float], scope: str, limit: int = 10 ) -> tuple[Ranked, ...]:

        return Ranking().fuse(self.dense(embedding, scope, limit), self.lexical(query, scope, limit))[:limit]

    def clear ( self, scope: str ) -> int:

        keys = [item.key for item in self.items(scope)]
        self._items = {key: item for key, item in self._items.items() if key not in keys}
        self._vectors = {key: item for key, item in self._vectors.items() if key not in keys}
        if not self._items: self._dimension = None
        return len(keys)
