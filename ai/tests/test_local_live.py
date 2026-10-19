from contextlib import aclosing
from pathlib import Path
from core.error import Fault
from core.llm import Catalog, Llm, Local
import asyncio
import pytest

@pytest.mark.live
@pytest.mark.anyio
async def test_native_lifecycle_stream_abort_restore_and_context ( tmp_path: Path ) -> None:

    models = await Catalog().load("src/usage/models.json")
    provider = Local(models["generation"], name="generation")
    engine = Llm()
    engine.register(provider)
    engine.setup(path=str(tmp_path))
    try:
        await asyncio.gather(*(engine.start("generation") for _ in range(3)))
        prompt = engine.use().temperature(0).max_tokens(64).session(name="Native lifecycle")
        key = prompt.session_id()
        assert key is not None
        async with aclosing(prompt.stream("Reply with exactly READY.")) as stream:
            async for chunk in stream:
                if chunk.text: break
        session = prompt.current()
        assert session is not None
        assert session.turns == 0
        result = await prompt.ask("Reply with exactly READY.")
        assert result.text.strip() == "READY"
        session = await engine.sessions.restore(key)
        assert session.turns == 1
        chunks = [chunk async for chunk in prompt.stream("Reply with exactly READY.")]
        assert "".join(chunk.text for chunk in chunks).strip() == "READY"
        assert sum(chunk.done for chunk in chunks) == 1
        session = await engine.sessions.restore(key)
        assert session.turns == 2
        compacted = await prompt.max_tokens(80).compact(keep=2)
        assert compacted.summary.strip()
        assert len(compacted.messages) == 2
        assert (await engine.sessions.restore(key)).summary == compacted.summary
        with pytest.raises(Fault) as caught:
            await engine.use().ask("word " * 5000)
        assert caught.value.reason in ("harness.input.limit", "llm.context.limit")
        await engine.close()
        await engine.start("generation")
        answer = await engine.use().temperature(0).max_tokens(16).ask("Reply with exactly READY.")
        assert answer.text.strip() == "READY"
    finally: await engine.close()
