from collections.abc import Callable
from pathlib import Path
from typing import Any
from core.error import Fault
from core.fs import Part
from core.json import json
from core.llm import Capabilities, Compatible, Llm
from core.rag import Document, Models, Rag
import asyncio
import pytest

@pytest.mark.anyio
async def test_failed_reindex_keeps_all_previous_chunks ( serve: Callable[..., str] ) -> None:

    failure = False
    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        if failure and body["input"] == ["second replacement"]: return 503, b"{}", {}
        return 200, json.encode({"data": [{"index": 0, "embedding": [1.0, 0.0]}]}), {}
    engine = Llm()
    engine.register(Compatible(serve(answer), model="fixture", capabilities=Capabilities(embed=True)))
    rag = Rag(Models(engine.use(), engine.use()))
    try:
        await rag.ingest([Document("same", "policy", (Part("original"),))], "tenant")
        failure = True
        with pytest.raises(Fault):
            document = Document("same", "policy", (Part("first replacement"), Part("second replacement")))
            await rag.ingest([document], "tenant")
        assert [item.text for item in await rag.retrieve("policy", "tenant")] == ["original"]
    finally: await engine.close()

@pytest.mark.anyio
async def test_independent_session_stores_share_a_durable_transaction_lock (
    tmp_path: Path, serve: Callable[..., str],
) -> None:

    lengths: list[int] = []
    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        lengths.append(len(body["messages"]))
        return 200, json.encode({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}), {}
    base = serve(answer)
    engines = [Llm(), Llm()]
    for engine in engines:
        engine.setup(path=str(tmp_path))
        engine.register(Compatible(base, model="fixture"))
    try:
        first = engines[0].use().session()
        await first.ask("initial")
        key = first.session_id()
        assert key is not None
        second = await engines[1].restore(key)
        await asyncio.gather(first.ask("a"), second.ask("b"), first.ask("c"), second.ask("d"))
        assert lengths == [1, 3, 5, 7, 9]
        assert (await engines[0].sessions.restore(key)).turns == 5
        assert (await engines[1].sessions.restore(key)).turns == 5
    finally:
        for engine in engines: await engine.close()
