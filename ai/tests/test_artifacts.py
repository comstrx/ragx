from collections.abc import Callable
from pathlib import Path
from typing import Any
from core.error import Fault
from core.fs import Artifact, Artifacts
from core.net import DownloadPolicy, Downloads
import asyncio, hashlib
import pytest

@pytest.mark.anyio
async def test_real_download_concurrency_integrity_and_repair (
    tmp_path: Path, serve: Callable[..., str],
) -> None:

    payload = b"verified model artifact" * 4096
    requests = 0

    def answer ( method: str, path: str, body: dict[str, Any] ) -> tuple[int, bytes, dict[str, str]]:

        nonlocal requests
        requests += 1
        return 200, payload, {}

    base = serve(answer)
    downloads = Downloads(DownloadPolicy(allow_loopback=True))
    spec = Artifact(hashlib.sha256(payload).hexdigest(), len(payload), "weights.gguf")
    store = Artifacts(tmp_path / "models")
    paths = await asyncio.gather(*[
        store.install(spec, lambda: downloads.chunks(base + "/weights")) for _ in range(5)
    ])
    assert len(set(paths)) == 1
    assert requests == 1
    assert paths[0].read_bytes() == payload
    paths[0].write_bytes(b"corrupt")
    await store.install(spec, lambda: downloads.chunks(base + "/weights"))
    assert requests == 2
    assert store.valid(spec)
    assert not list(tmp_path.glob("**/.partial-*"))

@pytest.mark.anyio
async def test_failed_download_never_publishes_and_can_retry ( tmp_path: Path ) -> None:

    payload = b"valid"
    spec = Artifact(hashlib.sha256(payload).hexdigest(), len(payload), "model.gguf")
    store = Artifacts(tmp_path)

    async def corrupt () -> Any:

        yield b"wrong"

    with pytest.raises(Fault) as caught:
        await store.install(spec, corrupt)
    assert caught.value.reason == "artifact.integrity"
    assert not store.target(spec).exists()
    assert not list(tmp_path.glob("**/.partial-*"))

    async def cancelled () -> Any:

        yield b"v"
        await asyncio.sleep(10)

    task = asyncio.create_task(store.install(spec, cancelled))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert not list(tmp_path.glob("**/.partial-*"))

@pytest.mark.anyio
async def test_download_blocks_untrusted_redirects ( serve: Callable[..., str] ) -> None:

    base = serve(lambda *_: (302, b"", {"location": "http://169.254.169.254/latest/meta-data"}))
    downloader = Downloads(DownloadPolicy(allow_loopback=True))
    with pytest.raises(Fault) as caught:
        async for _ in downloader.chunks(base): pass
    assert caught.value.reason == "download.origin"

def test_artifact_traversal_and_symlink_are_rejected ( tmp_path: Path ) -> None:

    digest = "a" * 64
    with pytest.raises(Fault): Artifact(digest, 1, "../escape")
    store = Artifacts(tmp_path / "root")
    store.root.mkdir()
    (store.root / digest).symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(Fault): store.target(Artifact(digest, 1, "model"))
