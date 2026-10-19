from collections.abc import Sequence
from dataclasses import replace
from typing import Any, override

from core.array import Item, Search
from core.error import Code, Fault
from core.number import Embedding
from .contract import Index, Passage, Row

class MemoryIndex(Index):

    name = "memory"

    def __init__ ( self, capacity: int = 10_000 ) -> None:

        self._search     = Search(capacity)
        self._passages   : dict[str, Passage] = {}
        self._documents  : dict[tuple[str, str], tuple[str, ...]] = {}
        self._identities : dict[str, str] = {}

    def matching ( self, scope: str, identity: str ) -> None:

        known = self._identities.get(scope)

        if known is not None and known != identity: raise Fault(Code.CONFLICT, reason="rag.index.identity")

    @override
    async def replace ( self, scope: str, document: str, rows: Sequence[Row], identity: str ) -> int:

        self.matching(self.scoped(scope), identity)

        stale = self._documents.get((scope, document), ())
        items = [Item(row.passage.id, scope, row.passage.text, row.embedding) for row in rows]

        self._search.upsert(items, stale)

        self._passages = { key: value for key, value in self._passages.items() if key not in stale }

        self._passages.update({ row.passage.id: row.passage for row in rows })

        if rows: self._documents[scope, document] = tuple(row.passage.id for row in rows)
        else: self._documents.pop((scope, document), None)

        self.settle(scope, identity)

        return len(rows)

    @override
    async def remove ( self, scope: str, document: str ) -> int:

        stale = self._documents.pop((self.scoped(scope), document), ())

        self._search.upsert((), stale)

        self._passages = { key: value for key, value in self._passages.items() if key not in stale }

        self.settle(scope, None)

        return len(stale)

    @override
    async def search (
        self, scope: str, query: str, embedding: Embedding, identity: str, limit: int,
    ) -> tuple[Passage, ...]:

        self.matching(self.scoped(scope), identity)

        hits = self._search.hybrid(query, embedding, scope, limit)

        return tuple(replace(self._passages[hit.key], score=hit.score) for hit in hits)

    @override
    async def documents ( self, scope: str ) -> list[str]:

        self.scoped(scope)

        return sorted(document for owner, document in self._documents if owner == scope)

    @override
    async def count ( self, scope: str ) -> int:

        return self._search.count(self.scoped(scope))

    @override
    async def clear ( self, scope: str ) -> int:

        stale   = { key for (owner, _), keys in self._documents.items() if owner == self.scoped(scope) for key in keys }
        cleared = self._search.clear(scope)

        self._passages  = { key: value for key, value in self._passages.items() if key not in stale }
        self._documents = { key: value for key, value in self._documents.items() if key[0] != scope }

        self.settle(scope, None)

        return cleared

    def settle ( self, scope: str, identity: str | None ) -> None:

        if self._search.count(scope) == 0: self._identities.pop(scope, None)
        elif identity is not None: self._identities[scope] = identity

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "passages": len(self._passages), "scopes": len(self._identities) }
