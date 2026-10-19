from core.error import Code, Fault
from core.json import json
from .contract import Passage

class Context:

    def build ( self, question: str, passages: tuple[Passage, ...], budget: int ) -> tuple[str, tuple[Passage, ...]]:

        selected: list[Passage] = []
        records: list[dict[str, object]] = []

        for passage in passages:
            record: dict[str, object] = {
                "id": f"S{len(records) + 1}", "source": passage.source, "page": passage.page,
                "second": passage.second, "content": passage.text,
            }
            proposed = {"question": question, "untrusted_sources": [*records, record]}
            if len(json.dumps(proposed)) > budget: continue
            records.append(record)
            selected.append(passage)

        if not selected: raise Fault(Code.VALIDATION, reason="rag.context.empty")

        return json.dumps({"question": question, "untrusted_sources": records}), tuple(selected)
