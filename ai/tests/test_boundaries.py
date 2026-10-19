from collections.abc import Callable
from pathlib import Path
from typing import Any
from core.error import Fault
from core.fs import Bundle, Part
from core.json import Shape, json
from core.llm import Attachment, Capabilities, Compatible, EmbeddingOptions, Llm, RankingOptions
from core.rag import Document, Models, Rag
import io, tarfile
import pytest

@pytest.mark.parametrize("schema", [
    {"properties": []},
    {"properties": {"child": {"additionalProperties": {"$ref": "https://example.com/external"}}}},
    {"additionalProperties": {"items": {"$ref": "https://example.com/external"}}},
])
def test_schema_rejects_invalid_or_nested_external_references ( schema: dict[str, Any] ) -> None:

    with pytest.raises(Fault): Shape(schema)

@pytest.mark.anyio
async def test_dedicated_operations_reject_unused_options_before_network ( serve: Callable[..., str] ) -> None:

    calls = 0
    def answer ( *_: object ) -> tuple[int, bytes, dict[str, str]]:

        nonlocal calls
        calls += 1
        return 200, b"{}", {}

    engine = Llm()
    provider = Compatible(serve(answer), model="dedicated")
    provider.capabilities = Capabilities(embed=True, rank=True, embedding_instruction=True)
    engine.register(provider)
    try:
        with pytest.raises(Fault): await engine.use().model("another").embed(["hello"])
        with pytest.raises(Fault): await engine.use().temperature(0.3).embed(["hello"])
        with pytest.raises(Fault): await engine.use().embed(["hello"], EmbeddingOptions(instruction="do it"))
        with pytest.raises(Fault): await engine.use().rank("q", ["d"], RankingOptions(instruction="ignored"))
        with pytest.raises(Fault): await engine.use().session().rank("q", ["d"])
        with pytest.raises(Fault): engine.register(provider, name="renamed")
        assert engine.names() == ["compatible"]
        assert calls == 0
    finally: await engine.close()

@pytest.mark.anyio
async def test_snapshot_rejects_cross_scope_reference_without_mutating_index (
    tmp_path: Path, serve: Callable[..., str],
) -> None:

    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        return 200, json.encode({"data": [{"index": i, "embedding": [1.0, 0.0]}
                                         for i, _ in enumerate(body["input"])]}), {}
    engine = Llm()
    provider = Compatible(serve(answer), model="fixture")
    provider.capabilities = Capabilities(embed=True)
    engine.register(provider)
    rag = Rag(Models(engine.use(), engine.use()))
    try:
        await rag.ingest([Document("d", "file", (Part("public"), Part("public")))], "a")
        await rag.ingest([Document("d", "file", (Part("secret"),))], "b")
        path = tmp_path / "index.json"
        await rag.save(path)
        await rag.load(path)
        valid = json.loads(path.read_text())
        damaged = json.loads(path.read_text())
        damaged["documents"][0]["passages"] = damaged["documents"][1]["passages"]
        path.write_text(json.dumps(damaged))
        with pytest.raises(Fault): await rag.load(path)
        assert [row.text for row in await rag.retrieve("public", "a")] == ["public", "public"]
        for field in ("records", "passages", "documents"):
            damaged = json.loads(json.dumps(valid))
            damaged[field].append(damaged[field][0])
            path.write_text(json.dumps(damaged))
            with pytest.raises(Fault): await rag.load(path)
    finally: await engine.close()

def test_bundle_rejects_added_libraries_and_modified_hardlinks ( tmp_path: Path ) -> None:

    archive = tmp_path / "bundle.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo("binary")
        member.size = 4
        stream.addfile(member, io.BytesIO(b"safe"))
        link = tarfile.TarInfo("linked")
        link.type, link.linkname = tarfile.LNKTYPE, "binary"
        stream.addfile(link)
    root = Bundle().unpack(archive, tmp_path / "runtime")
    Bundle().verify(archive, root, 100)
    (root / "linked").unlink()
    (root / "linked").write_bytes(b"evil")
    with pytest.raises(Fault): Bundle().verify(archive, root, 100)
    (root / "linked").write_bytes(b"safe")
    (root / "injected.so").write_bytes(b"evil")
    with pytest.raises(Fault): Bundle().verify(archive, root, 100)

@pytest.mark.anyio
async def test_attachment_detection_uses_content_and_rejects_mime_override ( tmp_path: Path ) -> None:

    target = tmp_path / "looks-like-an-image.png"
    target.write_text("This is text.")
    attachment = await Attachment.from_path(target)
    assert attachment.mime == "text/plain"
    with pytest.raises(Fault): await Attachment.from_path(target, "image/png")
    target.write_bytes(b"MZ" + bytes(100))
    with pytest.raises(Fault): await Attachment.from_path(target)
