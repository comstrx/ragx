from dataclasses import dataclass
from typing import Literal
from core.error import Code, Fault
from core.json import Shape, json
from .embedding import Score, scores

@dataclass(frozen=True, slots=True)
class RankingOptions:

    method      : Literal["dedicated", "generation"] = "dedicated"
    instruction : str | None = None
    native_schema : bool = False

def ranking_prompt ( query: str, documents: tuple[str, ...], instruction: str ) -> str:

    return json.dumps({
        "task": instruction, "query": query,
        "untrusted_documents": [{"index": index, "content": text} for index, text in enumerate(documents)],
    })

def ranking_result ( text: str, documents: tuple[str, ...] ) -> tuple[Score, ...]:

    result = scores(json.parse(text), documents)
    if any(not 0 <= item.score <= 1 for item in result):
        raise Fault(Code.UNAVAILABLE, reason="llm.rank.range")
    return result

def ranking_shape ( count: int ) -> Shape:

    return Shape({
        "type": "object", "additionalProperties": False, "required": ["results"],
        "properties": {"results": {
            "type": "array", "minItems": count, "maxItems": count,
            "items": {"type": "object", "additionalProperties": False, "required": ["index", "relevance_score"],
                     "properties": {"index": {"type": "integer", "minimum": 0, "maximum": count - 1},
                                    "relevance_score": {"type": "number", "minimum": 0, "maximum": 1}}},
        }},
    })
