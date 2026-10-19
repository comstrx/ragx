from collections.abc import Callable
from typing import Any
from core.error import Fault
from core.fs import Part
from core.json import json
from core.llm import Capabilities, Compatible, Llm
from core.rag import Document, Models, Rag
from core.rag.shapes import answer_shape
import pytest

@pytest.mark.anyio
async def test_rag_real_http_contract_scopes_citations_and_evaluation ( serve: Callable[..., str] ) -> None:

    bad_citation = False
    generations: list[dict[str, Any]] = []

    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        if path.endswith("/embeddings"):
            rows = [{"index": i, "embedding": [1.0, 0.0]} for i, _ in enumerate(body["input"])]
            return 200, json.encode({"data": rows}), {}
        if path.endswith("/rerank"):
            return 200, json.encode({"results": [
                {"index": i, "relevance_score": 1 / (i + 1)} for i, _ in enumerate(body["documents"])
            ]}), {}
        result: dict[str, Any]
        content = json.loads(body["messages"][-1]["content"])
        if "untrusted_sources" in content:
            generations.append(body)
            sources = content["untrusted_sources"]
            assert all("SECRET" not in item["content"] for item in sources)
            result = {"answer": "Refunds are allowed for 14 days.",
                      "citations": ["invented" if bad_citation else sources[0]["id"]]}
        else: result = {"score": 1.0, "reasoning": "Supported by the supplied policy."}
        return 200, json.encode({"model": "fixture", "choices": [
            {"message": {"content": json.dumps(result)}, "finish_reason": "stop"},
        ]}), {}

    engine = Llm()
    provider = Compatible(serve(answer), model="fixture")
    provider.capabilities = Capabilities(embed=True, rank=True, json=True, schema=True)
    engine.register(provider)
    prompt = engine.use()
    rag = Rag(Models(prompt, prompt, prompt, prompt))
    await rag.ingest([Document("policy", "refund.txt", (Part("Refunds are allowed for 14 days."),))], "tenant-a")
    await rag.ingest([Document("private", "private.txt", (Part("SECRET business data"),))], "tenant-b")
    result = await rag.ask("What is the refund period?", "tenant-a", generation=prompt.max_tokens(32))
    assert result.reply.text == "Refunds are allowed for 14 days."
    assert len(result.citations) == 1
    assert result.citations[0] == result.passages[0].id
    assert generations[0]["max_tokens"] == 32
    evaluation = await rag.evaluate("What is the refund period?", result)
    assert evaluation.score == 1
    bad_citation = True
    with pytest.raises(Fault) as caught: await rag.ask("refund", "tenant-a")
    assert caught.value.reason == "json.schema.output"
    assert await rag.clear("tenant-a") == 1
    assert not await rag.retrieve("refund", "tenant-a")
    assert len(await rag.retrieve("private", "tenant-b")) == 1
    await engine.close()

def test_grounded_answer_requires_at_least_one_permitted_citation () -> None:

    shape = answer_shape(("source-id",))
    with pytest.raises(Fault): shape.validate({"answer": "A factual assertion", "citations": []})
    with pytest.raises(Fault): shape.validate({"answer": "A factual assertion", "citations": ["unknown"]})
    shape.validate({"answer": "A factual assertion", "citations": ["source-id"]})
