from collections.abc import Callable
from pathlib import Path
from typing import Any
from core.error import Fault
from core.json import json
from core.llm import Compatible, Llm
import pytest

@pytest.mark.anyio
async def test_compaction_failure_is_atomic_and_success_preserves_rules_and_turns (
    tmp_path: Path, serve: Callable[..., str],
) -> None:

    fail = False
    bodies: list[dict[str, Any]] = []
    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        bodies.append(body)
        if fail: return 503, b"{}", {}
        return 200, json.encode({"choices": [{"message": {"content": "factual notes"}, "finish_reason": "stop"}]}), {}
    base = serve(answer)
    engine = Llm()
    engine.setup(path=str(tmp_path))
    engine.register(Compatible(base, model="fixture"))
    prompt = engine.use().system("Session rule").session()
    try:
        await prompt.ask("one")
        await prompt.ask("two")
        key = prompt.session_id()
        assert key is not None
        before = engine.sessions.resume(key).dump()
        fail = True
        with pytest.raises(Fault): await prompt.compact(keep=2)
        assert engine.sessions.resume(key).dump() == before
        fail = False
        compacted = await prompt.compact(keep=2)
        assert len(compacted.messages) == 2
        assert compacted.turns == 2
        assert compacted.summary == "factual notes"
        restored = await engine.restore(key)
        await restored.instruct("RAG rule").ask("three")
        system = bodies[-1]["messages"][0]["content"]
        assert "Session rule" in system
        assert "RAG rule" in system
        assert bodies[-1]["messages"][1]["role"] == "user"
        assert bodies[-1]["messages"][1]["content"].startswith("Untrusted conversation summary:")
    finally: await engine.close()
