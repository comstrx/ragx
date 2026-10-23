from pathlib import Path
from urllib.parse import urlsplit

from engine.error import Code
from engine.fs import LocalDriver, S3Driver, S3Options
from engine.net import Answer as Wired, Ask, Client as Remote, net
from engine.rand import rand
from engine.storage import Storage
from engine.test import expect, test
import os, pytest, re

PNG  = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
UUID = 36

def picture ( asked: Ask ) -> Wired:

    huge = urlsplit(asked.url).path.endswith("huge.png")

    return 200, PNG * (40 if huge else 1), { "content-type": "image/png" }

def remote () -> Remote:

    return Remote("http://far.test", transport=net.mocked(picture))

class Upload:

    def __init__ ( self, name: str, data: bytes, kind: str | None = None ) -> None:

        self.filename     = name
        self.content_type = kind
        self.size         = len(data)
        self._data        = data

    async def read ( self, size: int = -1 ) -> bytes:

        return self._data

@pytest.mark.anyio
class TestStorage:

    async def test_disks_dating_naming_and_the_upload_policy ( self, tmp_path: Path ) -> None:

        store = Storage()
        disks = {
            "public"  : LocalDriver(tmp_path / "public", "/static"),
            "private" : LocalDriver(tmp_path / "private"),
        }

        store.setup(disks, pattern="{Y}/{m}", blocked=("HTML", ".php"))

        expect(re.fullmatch(r"uploads/\d{4}/\d{2}", store.dated("uploads"))).truthy()
        expect(re.fullmatch(r"x/\d{4}/\d{3}", store.dated("x", "{Y}/{j}"))).truthy()
        expect(store.clean("/a//b/./c.txt")).equals("a/b/c.txt")
        expect(store.names()).equals(["private", "public"])
        expect(store.name("Photo Of Me.PNG", keep=True)).equals("photo-of-me.png")
        expect(store.name("x.jpeg")).ends_with(".jpeg")
        expect(len(store.name("x.jpeg"))).equals(UUID + len(".jpeg"))
        expect((store.mime("a.png"), store.mime("a.bin"))).equals(("image/png", "application/octet-stream"))
        expect(store.mime("a", "text/plain; charset=utf-8")).equals("text/plain")

        put = await store.put("docs/readme.txt", "hello")

        expect((put.disk, put.path, put.size, put.mime)).equals(("public", "docs/readme.txt", 5, "text/plain"))
        expect(put.url).equals("/static/docs/readme.txt")
        expect(put.name).equals("readme.txt")

        fetched = await store.fetch("http://far.test/pics/logo.png?v=1", "remote", name="logo.png", client=remote())
        dated   = await store.fetch("http://far.test/pics/logo.png", "remote", keep=True, client=remote(), pattern="")

        expect((fetched.mime, fetched.size, fetched.disk)).equals(("image/png", len(PNG), "public"))
        expect(re.fullmatch(r"remote/\d{4}/\d{2}/logo\.png", fetched.path)).truthy()
        expect(await store.exists(fetched.path)).truthy()
        expect(dated.path).equals("remote/logo.png")
        expect(await store.get(dated.path)).equals(PNG)

        huge = store.fetch("http://far.test/pics/huge.png", "remote", client=remote(), limit=len(PNG))

        await test.rejects(huge, Code.VALIDATION, field="file")

        await store.put("logs/a/one.txt", "1")
        await store.put("logs/b/two.txt", "2")
        await store.put("logs/root.txt", "r")

        expect(await store.files("logs")).equals(["logs/root.txt"])
        expect(await store.directories("logs")).equals(["logs/a", "logs/b"])
        expect(await store.missing("logs/none.txt")).truthy()
        expect(await store.missing("logs/root.txt")).falsy()
        expect((await store.append("logs/root.txt", "+")).size).equals(2)
        expect((await store.prepend("logs/root.txt", "<")).size).equals(3)
        expect(await store.text("logs/root.txt")).equals("<r+")
        expect(await store.last_modified("logs/root.txt")).above(0)
        expect(await store.delete_directory("logs/a")).equals(1)
        expect(await store.directories("logs")).equals(["logs/b"])
        expect(await store.directories()).contains("docs")
        expect((await store.append("fresh/new.txt", "n")).size).equals(1)
        expect(await store.text("fresh/new.txt")).equals("n")

        expect(await store.text("docs/readme.txt")).equals("hello")
        expect(await store.exists("docs/readme.txt")).truthy()
        expect(await store.size("docs/readme.txt")).equals(5)
        expect(store.local("docs/readme.txt")).equals(tmp_path / "public" / "docs" / "readme.txt")

        stored = await store.upload(Upload("Cat.PNG", PNG, "image/png"), "avatars", allowed=("image/*",))
        kept   = await store.upload(Upload("Cat.PNG", PNG), "raw", disk="private", pattern="", keep=True)

        expect(stored.path).starts_with("avatars/")
        expect(stored.path).ends_with(".png")
        expect(stored.mime).equals("image/png")
        expect(stored.url).some().starts_with("/static/avatars/")
        expect((kept.path, kept.url, kept.disk)).equals(("raw/cat.png", None, "private"))
        expect(await store.exists("raw/cat.png", "private")).truthy()

        with test.fails(Code.INTERNAL, "fs.local.config.url"): store.url("raw/cat.png", "private")

        signed = store.temporary_url("raw/cat.png", 60, "private")

        await test.rejects(signed, Code.INTERNAL, "fs.local.unsupported.sign")
        await test.rejects(disks["private"].get("../public/docs/readme.txt"), Code.BAD_REQUEST, "fs.path")

        bucket = S3Driver("unit-bucket")

        with test.fails(Code.INTERNAL, "fs.s3.unsupported.path"): bucket.local("a.txt")

        expect(store.disk("public").describe()).equals({
            "family": "fs", "name": "local", "capabilities": ["files", "list", "path", "stream"], "public": True,
        })
        expect(bucket.describe()["capabilities"]).equals(["files", "list", "sign", "stream"])

        await store.copy("docs/readme.txt", "docs/copy.txt")
        await store.move("docs/copy.txt", "docs/moved.txt")

        chunks = await store.stream("docs/readme.txt")

        expect(await store.list("docs")).equals(["docs/moved.txt", "docs/readme.txt"])
        expect(await store.delete("docs/moved.txt")).truthy()
        expect(await store.delete("docs/moved.txt")).falsy()
        expect(b"".join([chunk async for chunk in chunks])).equals(b"hello")

        for file, policy, message in (
            (Upload("x.exe", b"MZ", "application/x-msdownload"), { "allowed": ("image/*",) }, "Expected one of"),
            (Upload("x.png", b"", "image/png"), {}, "empty"),
            (Upload("x.png", PNG, "image/png"), { "limit": 8 }, "exceeds"),
            (Upload("page.HTML", b"<h1>", "text/html"), {}, "not accepted"),
        ):

            refused = await test.rejects(store.upload(file, "x", **policy), Code.VALIDATION, field="file")

            expect((refused.errors or {})["file"][0]).contains(message)

        with test.fails(Code.BAD_REQUEST, "storage.path"): store.clean("../etc/passwd")
        with test.fails(Code.INTERNAL, "storage.nowhere.missing"): store.disk("nowhere")

        await test.rejects(store.get("docs/none.txt"), Code.NOT_FOUND, "fs.missing")

    async def test_an_s3_disk_keeps_the_same_contract_on_a_real_bucket ( self ) -> None:

        names = ("S3_TEST_ENDPOINT", "S3_TEST_KEY", "S3_TEST_SECRET", "S3_TEST_BUCKET")
        given = [os.environ.get(name, "") for name in names]

        if not all(given): pytest.skip(f"set {' '.join(names)} to exercise a real S3 bucket")

        endpoint, key, secret, name = given
        region  = os.environ.get("S3_TEST_REGION", "us-east-1")
        options = S3Options(region=region, endpoint=endpoint, key=key, secret=secret, path_style=True)
        bucket  = S3Driver(name, options, f"{endpoint}/{name}")
        store   = Storage()
        root    = f"lab-{rand.hex(4)}"

        store.setup({ "s3": bucket }, default="s3", pattern="")

        try:

            put = await store.put(f"{root}/docs/readme.txt", "hello")

            expect((put.disk, put.size, put.mime, put.url)).equals(
                ("s3", 5, "text/plain", f"{endpoint}/{name}/{root}/docs/readme.txt"),
            )
            expect((await store.text(put.path), await store.size(put.path), await store.exists(put.path))).equals(
                ("hello", 5, True),
            )
            expect(await store.last_modified(put.path)).above(0)

            await store.put(f"{root}/logs/a/one.txt", "1")
            await store.put(f"{root}/logs/root.txt", "r")

            expect(await store.files(f"{root}/logs")).equals([f"{root}/logs/root.txt"])
            expect(await store.directories(f"{root}/logs")).equals([f"{root}/logs/a"])
            expect((await store.append(f"{root}/logs/root.txt", "+")).size).equals(2)
            expect(await store.text(f"{root}/logs/root.txt")).equals("r+")

            await store.copy(put.path, f"{root}/docs/copy.txt")
            await store.move(f"{root}/docs/copy.txt", f"{root}/docs/moved.txt")

            chunks = await store.stream(put.path)

            expect(await store.list(f"{root}/docs")).equals([f"{root}/docs/moved.txt", f"{root}/docs/readme.txt"])
            expect(b"".join([chunk async for chunk in chunks])).equals(b"hello")
            expect(await store.delete(f"{root}/docs/moved.txt")).truthy()
            expect(await store.delete(f"{root}/docs/moved.txt")).falsy()

            stored = await store.upload(Upload("Cat.PNG", PNG, "image/png"), f"{root}/avatars", allowed=("image/*",))
            signed = await store.temporary_url(stored.path, 60)
            client = Remote()

            try: fetched = await client.get(signed)
            finally: await client.close()

            expect((fetched.status, fetched.body)).equals((200, PNG))

            await test.rejects(store.get(f"{root}/none.txt"), Code.NOT_FOUND, "fs.missing")
            await test.rejects(store.stream(f"{root}/none.txt"), Code.NOT_FOUND, "fs.missing")
            await test.rejects(bucket.get(f"{root}/../escape.txt"), Code.BAD_REQUEST, "fs.path")
            await test.rejects(bucket.put(f"{root}/../escape.txt", b"x", "text/plain"), Code.BAD_REQUEST, "fs.path")

            denied = S3Options(region=region, endpoint=endpoint, key=key, secret="wrong", path_style=True)
            wrong  = S3Driver(name, denied)
            gone   = S3Driver(f"{name}-missing-{rand.hex(3)}", options)

            await test.rejects(wrong.get(put.path), Code.INTERNAL, "fs.s3.denied")
            await test.rejects(gone.put("a.txt", b"x", "text/plain"), Code.INTERNAL, "fs.s3.bucket")

        finally:

            expect(await store.delete_directory(root)).above(0)
            expect(await store.list(root)).equals([])
