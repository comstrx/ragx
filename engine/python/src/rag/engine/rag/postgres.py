from collections.abc import Callable, Sequence
from typing import Any, ClassVar, override

from engine.database import Blueprint, Database, Embedded
from engine.error import Code, Fault
from engine.json import json
from engine.number import Embedding, Vector
from engine.string import string
from .contract import DENSE, DURABLE, LEXICAL, Index, Passage, Row
import sqlalchemy as sa

FUSION  = 60
BATCH   = 200
POOL    = 1000
LOCK    = "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"
NEAREST = (
    "EXPLAIN SELECT id FROM {table} WHERE scope = :scope ORDER BY embedding <=> CAST(:vector AS vector) LIMIT :limit"
)
VECTORS = Vector()
SEARCH  = """
WITH dense AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:vector AS vector)) AS position
    FROM {table} WHERE scope = :scope
    ORDER BY embedding <=> CAST(:vector AS vector) LIMIT :limit
), pool AS (
    SELECT id, lexemes FROM {table}, to_tsquery('simple', :terms) AS asked
    WHERE scope = :scope AND lexemes @@ asked LIMIT :pool
), lexical AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank(lexemes, asked) DESC, id) AS position
    FROM pool, to_tsquery('simple', :terms) AS asked
    ORDER BY ts_rank(lexemes, asked) DESC, id LIMIT :limit
)
SELECT found.id, found.document, found.source, found.text, found.page, found.second, found.start, found.stop,
    COALESCE(1.0 / (:fusion + dense.position), 0) + COALESCE(1.0 / (:fusion + lexical.position), 0) AS score
FROM dense FULL OUTER JOIN lexical USING (id) JOIN {table} AS found USING (id)
ORDER BY score DESC, found.id LIMIT :limit
"""

def shaped ( name: str ) -> sa.TableClause:

    return sa.table(
        name, *(sa.column(key, sa.String()) for key in ("id", "scope", "document", "source", "text", "identity")),
        sa.column("page", sa.Integer()), sa.column("second", sa.Float()), sa.column("start", sa.Integer()),
        sa.column("stop", sa.Integer()), sa.column("terms", sa.Text()), sa.column("embedding", sa.Text()),
    )

def literal ( embedding: Embedding ) -> str:

    return "[" + ",".join(map(repr, embedding)) + "]"

class PostgresIndex(Index):

    name         = "postgres"
    capabilities : ClassVar[frozenset[str]] = frozenset({DENSE, LEXICAL, DURABLE})

    def __init__ (
        self, database: Database, table: str = "rag_passages", dimension: int = 1024, fusion: int = FUSION,
    ) -> None:

        if not table.replace("_", "").isalnum() or dimension < 1: raise Fault(Code.INTERNAL, reason="rag.postgres")

        self._database  = database
        self._name      = table
        self._table     = shaped(table)
        self._dimension = dimension
        self._fusion    = fusion

    @staticmethod
    def define ( dimension: int ) -> Callable[[Blueprint], None]:

        def define ( table: Blueprint ) -> None:

            table.string("id", 64).key()
            table.string("scope", 255)
            table.string("document", 255)
            table.text("source")
            table.text("text")
            table.integer("page").nullable()
            table.float("second").nullable()
            table.integer("start")
            table.integer("stop")
            table.string("identity", 255)
            table.text("terms")
            table.vector("embedding", dimension)
            table.tsvector("lexemes").generated("to_tsvector('simple'::regconfig, terms)")
            table.timestamp("created_at").default(sa.func.now())
            table.index(["scope", "document"])
            table.gin("lexemes")
            table.nearest("embedding")

        return define

    def sized ( self, embedding: Embedding ) -> Embedding:

        if len(embedding) != self._dimension: raise Fault(Code.VALIDATION, reason="rag.index.dimension")

        return VECTORS.of(embedding)

    async def matching ( self, scope: str, identity: str ) -> None:

        table = self._table
        known = await self._database.value(sa.select(table.c.identity).where(table.c.scope == scope).limit(1))

        if known is not None and known != identity: raise Fault(Code.CONFLICT, reason="rag.index.identity")

    def record ( self, scope: str, row: Row, identity: str ) -> dict[str, Any]:

        passage = row.passage
        vector  = sa.cast(sa.literal(literal(self.sized(row.embedding)), sa.Text()), Embedded(self._dimension))

        return {
            "id": passage.id, "scope": scope, "document": passage.document, "source": passage.source,
            "text": passage.text, "page": passage.page, "second": passage.second, "start": passage.start,
            "stop": passage.end, "identity": identity, "terms": " ".join(string.terms(passage.text)),
            "embedding": vector,
        }

    @override
    async def replace ( self, scope: str, document: str, rows: Sequence[Row], identity: str ) -> int:

        table   = self._table
        records = [self.record(self.scoped(scope), row, identity) for row in rows]

        async with self._database.transaction() as session:

            await session.script(LOCK, { "key": json.dumps(["rag", self._name, scope]) })
            await self.matching(scope, identity)
            await self._database.execute(sa.delete(table).where(table.c.scope == scope, table.c.document == document))

            for start in range(0, len(records), BATCH):
                await self._database.execute(sa.insert(table).values(records[start:start + BATCH]))

        return len(records)

    @override
    async def remove ( self, scope: str, document: str ) -> int:

        table = self._table

        return await self._database.execute(
            sa.delete(table).where(table.c.scope == self.scoped(scope), table.c.document == document),
        )

    @override
    async def search (
        self, scope: str, query: str, embedding: Embedding, identity: str, limit: int,
    ) -> tuple[Passage, ...]:

        terms = " | ".join(dict.fromkeys(string.terms(query)))
        asked = {
            "vector": literal(self.sized(embedding)), "scope": self.scoped(scope), "terms": terms, "limit": limit,
            "fusion": self._fusion, "pool": POOL,
        }

        async with self._database.transaction() as session:

            await self.matching(scope, identity)
            await session.script("SET LOCAL hnsw.iterative_scan = relaxed_order")

            rows = await self._database.fetch(sa.text(SEARCH.format(table=self._name)), asked)

        return tuple(
            Passage(
                str(row["id"]), str(row["document"]), str(row["source"]), str(row["text"]), row["page"], row["second"],
                int(row["start"]), int(row["stop"]), float(row["score"]),
            ) for row in rows
        )

    async def explain ( self, scope: str, embedding: Embedding, limit: int = 8 ) -> list[str]:

        asked = { "scope": self.scoped(scope), "vector": literal(self.sized(embedding)), "limit": limit }

        async with self._database.transaction() as session:

            await session.script("SET LOCAL hnsw.iterative_scan = relaxed_order")

            rows = await self._database.fetch(sa.text(NEAREST.format(table=self._name)), asked)

        return [str(next(iter(row.values()))) for row in rows]

    @override
    async def documents ( self, scope: str ) -> list[str]:

        table = self._table
        found = sa.select(table.c.document).where(table.c.scope == self.scoped(scope)).distinct()

        return [str(row["document"]) for row in await self._database.fetch(found.order_by(table.c.document))]

    @override
    async def count ( self, scope: str ) -> int:

        table = self._table
        found = sa.select(sa.func.count()).select_from(table).where(table.c.scope == self.scoped(scope))

        return int(await self._database.value(found) or 0)

    @override
    async def clear ( self, scope: str ) -> int:

        table = self._table

        return await self._database.execute(sa.delete(table).where(table.c.scope == self.scoped(scope)))

    @override
    def describe ( self ) -> dict[str, Any]:

        return { **super().describe(), "table": self._name, "dimension": self._dimension, "fusion": self._fusion }
