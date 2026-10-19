from collections.abc import Sequence
from dataclasses import dataclass, field
from core.error import Code, Fault
from core.number import vector
from .message import Usage

@dataclass(frozen=True, slots=True)
class EmbeddingOptions:

    instruction : str | None = None
    query       : bool = False

@dataclass(frozen=True, slots=True)
class Embeddings:

    vectors  : tuple[tuple[float, ...], ...]
    model    : str
    provider : str
    usage    : Usage = field(default_factory=Usage)

    @classmethod
    def parse ( cls, data: object, expected: int, model: str, provider: str ) -> Embeddings:

        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise Fault(Code.UNAVAILABLE, reason="llm.embedding.response")

        rows = data["data"]
        if len(rows) != expected: raise Fault(Code.UNAVAILABLE, reason="llm.embedding.count")
        indexed: dict[int, tuple[float, ...]] = {}
        dimension: int | None = None

        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("embedding"), list):
                raise Fault(Code.UNAVAILABLE, reason="llm.embedding.vector")
            index = row.get("index")
            if type(index) is not int or index in indexed or index not in range(expected):
                raise Fault(Code.UNAVAILABLE, reason="llm.embedding.index")
            values = vector.validate(row["embedding"], dimension)
            dimension = len(values)
            indexed[index] = values

        return cls(tuple(indexed[index] for index in range(expected)), model, provider)

@dataclass(frozen=True, slots=True)
class Score:

    index : int
    score : float

def scores ( data: object, documents: Sequence[str] ) -> tuple[Score, ...]:

    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise Fault(Code.UNAVAILABLE, reason="llm.rank.response")

    result: list[Score] = []
    seen: set[int] = set()

    for row in data["results"]:
        if not isinstance(row, dict): raise Fault(Code.UNAVAILABLE, reason="llm.rank.row")
        index = row.get("index")
        value = row.get("relevance_score")
        if type(index) is not int or index not in range(len(documents)) or index in seen:
            raise Fault(Code.UNAVAILABLE, reason="llm.rank.index")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise Fault(Code.UNAVAILABLE, reason="llm.rank.score")
        vector.validate([value])
        seen.add(index)
        result.append(Score(index, float(value)))

    if len(result) != len(documents): raise Fault(Code.UNAVAILABLE, reason="llm.rank.count")

    return tuple(sorted(result, key=lambda item: (-item.score, item.index)))
