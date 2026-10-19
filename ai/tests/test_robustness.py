from collections.abc import Callable
from pathlib import Path
from typing import Any
from core.error import Fault
from core.fs import Bundle
from core.json import Shape, json
from core.llm import Attachment, Capabilities, Compatible, Harness, Llm
from core.rag import Document, Models, Rag
from core.fs import Part
import asyncio, io, tarfile
import pytest

def test_schema_blocks_remote_references_and_invalid_output () -> None:

    with pytest.raises(Fault): Shape({"$ref": "https://example.com/schema"})
    shape = Shape({"type": "object", "properties": {"score": {"type": "number", "minimum": 0, "maximum": 1}},
                   "required": ["score"], "additionalProperties": False})
    shape.validate({"score": 0.5})
    with pytest.raises(Fault): shape.validate({"score": 2})

def test_policy_cannot_be_relaxed_or_apply_text_redaction_to_binary () -> None:

    strict = Harness(redact=True, max_output_tokens=10, timeout=2)
    relaxed = Harness(redact=False, max_output_tokens=1000, timeout=200)
    policy = strict.merge(relaxed)
    assert policy.redact
    assert policy.max_output_tokens == 10
    assert policy.timeout == 2
    with pytest.raises(Fault): policy.attachment(Attachment("photo", b"image", "image/png"))

def test_bundle_rechecks_existing_executable ( tmp_path: Path ) -> None:

    archive = tmp_path / "runtime.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("llama-server")
        member.size = 4
        stream.addfile(member, io.BytesIO(b"safe"))
    root = Bundle().unpack(archive, tmp_path / "runtime")
    (root / "llama-server").write_bytes(b"evil")
    with pytest.raises(Fault) as caught: Bundle().unpack(archive, root)
    assert caught.value.reason == "bundle.integrity"

@pytest.mark.anyio
async def test_in_memory_sessions_serialize_after_replacement ( serve: Callable[..., str] ) -> None:

    counts: list[int] = []
    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        counts.append(len(body["messages"]))
        return 200, json.encode({"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}]}), {}
    engine = Llm()
    engine.register(Compatible(serve(answer), model="fixture"))
    prompt = engine.use().session()
    await asyncio.gather(*(prompt.ask(str(index)) for index in range(10)))
    assert counts == list(range(1, 20, 2))
    session = prompt.current()
    assert session is not None
    assert session.turns == 10
    await engine.close()

@pytest.mark.anyio
async def test_reindex_replaces_old_chunks_and_snapshot_rejects_wrong_model (
    tmp_path: Path, serve: Callable[..., str],
) -> None:

    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        return 200, json.encode({"data": [{"index": i, "embedding": [1.0, 0.0]}
                                         for i, _ in enumerate(body["input"])]}), {}
    engine = Llm()
    provider = Compatible(serve(answer), model="embedding-v1")
    provider.capabilities = Capabilities(embed=True, json=True)
    engine.register(provider)
    rag = Rag(Models(engine.use(), engine.use()))
    await rag.ingest([Document("policy", "policy", (Part("Old policy"),))], "tenant")
    await rag.ingest([Document("policy", "policy", (Part("New policy"),))], "tenant")
    assert [item.text for item in await rag.retrieve("policy", "tenant")] == ["New policy"]
    path = str(tmp_path / "index.json")
    await rag.save(path)
    restored = Rag(Models(engine.use(), engine.use()))
    await restored.load(path)
    assert [item.text for item in await restored.retrieve("policy", "tenant")] == ["New policy"]
    provider.model = "embedding-v2"
    with pytest.raises(Fault): await rag.retrieve("policy", "tenant")
    changed = Rag(Models(engine.use(), engine.use()))
    with pytest.raises(Fault): await changed.load(path)
    await engine.close()
