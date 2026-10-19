from dataclasses import dataclass
from typing import Any
from core.array import Search, SearchItem
from core.error import Code, Fault
from core.json import Shape
from core.number import vector
from .contract import Passage

def object_shape ( properties: dict[str, Any] ) -> dict[str, Any]:

    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}

def schema () -> Shape:

    text = {"type": "string"}
    identifier = {"type": "string", "minLength": 1}
    record = object_shape({
        "key": identifier, "scope": identifier, "text": text,
        "embedding": {"type": "array", "items": {"type": "number"}, "minItems": 1},
    })
    passage = object_shape({
        "id": identifier, "source": text, "text": text, "page": {"type": ["integer", "null"], "minimum": 1},
        "second": {"type": ["number", "null"], "minimum": 0}, "start": {"type": "integer", "minimum": 0},
        "end": {"type": "integer", "minimum": 0}, "score": {"type": "number"},
    })
    document = object_shape({
        "scope": identifier, "document": identifier, "passages": {"type": "array", "items": identifier},
    })
    return Shape(object_shape({
        "schema": {"enum": [1]}, "embedding": identifier,
        "records": {"type": "array", "items": record},
        "passages": {"type": "array", "items": passage},
        "documents": {"type": "array", "items": document},
    }))

@dataclass(frozen=True, slots=True)
class Snapshot:

    search    : Search
    passages  : dict[str, Passage]
    documents : dict[tuple[str, str], tuple[str, ...]]

    @classmethod
    def parse ( cls, data: dict[str, Any], identity: str, capacity: int ) -> Snapshot:

        schema().validate(data)
        if data["embedding"] != identity: raise Fault(Code.CONFLICT, reason="rag.index.identity")
        records = [SearchItem(row["key"], row["scope"], row["text"], tuple(row["embedding"]))
                   for row in data["records"]]
        items = {item.key: item for item in records}
        passages = {row["id"]: Passage(**row) for row in data["passages"]}
        documents = {(row["scope"], row["document"]): tuple(row["passages"]) for row in data["documents"]}
        if len(items) != len(records) or len(passages) != len(data["passages"]):
            raise Fault(Code.VALIDATION, reason="rag.index.duplicate")
        if len(documents) != len(data["documents"]) or items.keys() != passages.keys():
            raise Fault(Code.VALIDATION, reason="rag.index.references")
        referenced: set[str] = set()
        for (scope, _), keys in documents.items():
            for key in keys:
                if key in referenced or key not in items or items[key].scope != scope:
                    raise Fault(Code.VALIDATION, reason="rag.index.scope")
                referenced.add(key)
        if referenced != items.keys(): raise Fault(Code.VALIDATION, reason="rag.index.orphans")
        for key, passage in passages.items():
            vector.validate([passage.score, passage.second or 0])
            if items[key].text != passage.text or passage.end - passage.start != len(passage.text):
                raise Fault(Code.VALIDATION, reason="rag.index.passage")
        search = Search(identity, capacity)
        search.upsert(records)
        return cls(search, passages, documents)
