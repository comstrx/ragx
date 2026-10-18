from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.responses import Response
from core.error import Code, Fault
from core.http import App
from core.net import Client
from core.rand import rand
from core.storage import LocalDisk, Storage, storage
from config import StorageConfig
import pytest, re

PNG  = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
UUID = 36
far  = FastAPI()

@far.get("/pics/{name}")
async def picture ( name: str ) -> Response:
    return Response(PNG * (40 if name == "huge.png" else 1), media_type="image/png")

def remote () -> Client:
    return Client("http://far.test", transport=ASGITransport(app=far))

class Upload:

    def __init__ ( self, name: str, data: bytes, kind: str | None = None ) -> None:

        self.filename     = name
        self.content_type = kind
        self.size         = len(data)
        self._data        = data

    async def read ( self, size: int = -1 ) -> bytes:
        return self._data

async def member ( client: AsyncClient, tag: str ) -> dict[str, str]:

    body    = { "name": f"Owner {tag}", "email": f"owner-{tag}@unit.test", "password": f"Str0ng-{tag}-pass" }
    origin  = { "X-Forwarded-For": f"10.8.{len(tag)}.{tag[0:1].encode()[0]}" }
    created = await client.post("/v1/auth/register", json=body, headers=origin)

    assert created.status_code == 201

    return { "Authorization": f"Bearer {created.json()['data']['access_token']}" }

@pytest.mark.anyio
class TestStorage:

    async def test_disks_dating_naming_and_the_upload_policy ( self, tmp_path: Path ) -> None:

        store = Storage()
        disks = {
            "public"  : LocalDisk("public", tmp_path / "public", "/static"),
            "private" : LocalDisk("private", tmp_path / "private"),
        }

        store.setup(disks, pattern="{Y}/{m}", blocked=("HTML", ".php"))

        assert re.fullmatch(r"uploads/\d{4}/\d{2}", store.dated("uploads"))
        assert re.fullmatch(r"x/\d{4}/\d{3}", store.dated("x", "{Y}/{j}"))
        assert store.clean("/a//b/./c.txt") == "a/b/c.txt" and store.names() == ["private", "public"]
        assert store.name("Photo Of Me.PNG", keep=True) == "photo-of-me.png"
        assert store.name("x.jpeg").endswith(".jpeg") and len(store.name("x.jpeg")) == UUID + len(".jpeg")
        assert (store.mime("a.png"), store.mime("a.bin")) == ("image/png", "application/octet-stream")
        assert store.mime("a", "text/plain; charset=utf-8") == "text/plain"

        put = await store.put("docs/readme.txt", "hello")

        assert (put.disk, put.path, put.size, put.mime) == ("public", "docs/readme.txt", 5, "text/plain")
        assert put.url == "/static/docs/readme.txt" and put.name == "readme.txt"

        fetched = await store.fetch("http://far.test/pics/logo.png?v=1", "remote", name="logo.png", client=remote())
        dated   = await store.fetch("http://far.test/pics/logo.png", "remote", keep=True, client=remote(), pattern="")

        assert (fetched.mime, fetched.size, fetched.disk) == ("image/png", len(PNG), "public")
        assert re.fullmatch(r"remote/\d{4}/\d{2}/logo\.png", fetched.path) and await store.exists(fetched.path)
        assert dated.path == "remote/logo.png" and await store.get(dated.path) == PNG

        with pytest.raises(Fault) as oversize:
            await store.fetch("http://far.test/pics/huge.png", "remote", client=remote(), limit=len(PNG))

        assert oversize.value.code == Code.VALIDATION

        await store.put("logs/a/one.txt", "1")
        await store.put("logs/b/two.txt", "2")
        await store.put("logs/root.txt", "r")

        assert await store.files("logs") == ["logs/root.txt"]
        assert await store.directories("logs") == ["logs/a", "logs/b"]
        assert await store.missing("logs/none.txt") and not await store.missing("logs/root.txt")
        assert (await store.append("logs/root.txt", "+")).size == 2
        assert (await store.prepend("logs/root.txt", "<")).size == 3 and await store.text("logs/root.txt") == "<r+"
        assert await store.last_modified("logs/root.txt") > 0 and await store.delete_directory("logs/a") == 1
        assert await store.directories("logs") == ["logs/b"] and "docs" in await store.directories()
        assert await store.append("fresh/new.txt", "n") and await store.text("fresh/new.txt") == "n"

        assert await store.text("docs/readme.txt") == "hello" and await store.exists("docs/readme.txt")
        assert await store.size("docs/readme.txt") == 5
        assert store.local("docs/readme.txt") == tmp_path / "public" / "docs" / "readme.txt"

        stored = await store.upload(Upload("Cat.PNG", PNG, "image/png"), "avatars", allowed=("image/*",))
        kept   = await store.upload(Upload("Cat.PNG", PNG), "raw", disk="private", pattern="", keep=True)

        assert stored.path.startswith("avatars/") and stored.path.endswith(".png") and stored.mime == "image/png"
        assert stored.url is not None and stored.url.startswith("/static/avatars/")
        assert (kept.path, kept.url, kept.disk) == ("raw/cat.png", None, "private")
        assert store.url("raw/cat.png", "private") is None and await store.exists("raw/cat.png", "private")

        await store.copy("docs/readme.txt", "docs/copy.txt")
        await store.move("docs/copy.txt", "docs/moved.txt")

        chunks = await store.stream("docs/readme.txt")

        assert await store.list("docs") == ["docs/moved.txt", "docs/readme.txt"]
        assert await store.delete("docs/moved.txt") and not await store.delete("docs/moved.txt")
        assert b"".join([chunk async for chunk in chunks]) == b"hello"

        for file, policy, message in (
            (Upload("x.exe", b"MZ", "application/x-msdownload"), { "allowed": ("image/*",) }, "Expected one of"),
            (Upload("x.png", b"", "image/png"), {}, "empty"),
            (Upload("x.png", PNG, "image/png"), { "limit": 8 }, "exceeds"),
            (Upload("page.HTML", b"<h1>", "text/html"), {}, "not accepted"),
        ):

            with pytest.raises(Fault) as refused: await store.upload(file, "x", **policy)

            assert refused.value.code == Code.VALIDATION
            assert message in (refused.value.errors or {})["file"][0]

        paths = StorageConfig(root="../shared", public="pub", private="/var/private", logs="logs")

        assert paths.public_path(tmp_path / "api") == (tmp_path / "shared" / "pub").resolve()
        assert paths.private_path(tmp_path / "api") == Path("/var/private")
        assert paths.logs_path(tmp_path / "api") == (tmp_path / "shared" / "logs").resolve()
        assert StorageConfig().public_path(tmp_path) == tmp_path / "src" / "storage" / "app" / "public"

        with pytest.raises(Fault) as escape: store.clean("../etc/passwd")
        with pytest.raises(Fault) as unknown: store.disk("nowhere")
        with pytest.raises(Fault) as absent: await store.get("docs/none.txt")

        assert (escape.value.code, unknown.value.code) == (Code.BAD_REQUEST, Code.INTERNAL)
        assert absent.value.code == Code.NOT_FOUND

    async def test_public_files_are_served_and_private_files_need_their_owner (
        self, client: AsyncClient, app: App,
    ) -> None:

        tag    = rand.hex(4)
        owner  = await member(client, tag)
        other  = await member(client, rand.hex(4))
        shared = await client.post("/v1/files", files={ "file": ("Cat.PNG", PNG, "image/png") }, headers=owner)
        public = shared.json()["data"]
        served = await client.get(public["url"])
        secret = { "file": ("secret.txt", b"top", "text/plain") }
        kept   = await client.post("/v1/files/private", files=secret, headers=owner)
        hidden = kept.json()["data"]

        try:

            assert shared.status_code == 201 and public["mime"] == "image/png"
            assert public["url"].startswith("/storage/uploads/")
            assert served.status_code == 200 and served.content == PNG and served.headers["content-type"] == "image/png"
            assert kept.status_code == 201 and hidden["url"] is None and hidden["path"].startswith("users/")
            assert (await client.get(f"/storage/{hidden['path']}")).status_code == 404

            opened   = await client.get(f"/v1/files/{hidden['path']}", headers=owner)
            stranger = await client.get(f"/v1/files/{hidden['path']}", headers=other)
            nobody   = await client.get(f"/v1/files/{hidden['path']}")
            unsent   = await client.post("/v1/files", headers=owner)
            guest    = await client.post("/v1/files", files={ "file": ("a.txt", b"a", "text/plain") })

            assert opened.status_code == 200 and opened.content == b"top"
            assert opened.headers["content-type"].startswith("text/plain")
            assert (stranger.status_code, nobody.status_code) == (404, 401)
            assert (unsent.status_code, guest.status_code) == (422, 401)

        finally:

            await storage.delete(public["path"], "public")
            await storage.delete(hidden["path"], "private")
