from core.error import Code
from core.fs import Path
from core.http import App
from core.rand import rand
from core.storage import storage
from core.test import Client, expect
from config import StorageConfig

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

async def member ( client: Client, tag: str ) -> tuple[dict[str, str], str]:

    body    = { "name": f"Owner {tag}", "email": f"owner-{tag}@unit.test", "password": f"Str0ng-{tag}-pass" }
    origin  = { "X-Forwarded-For": f"10.8.{len(tag)}.{tag[0:1].encode()[0]}" }
    created = (await client.post("/v1/auth/register", json=body, headers=origin)).created()

    return { "Authorization": f"Bearer {created.data('access_token')}" }, str(created.data("user.id"))

class TestFiles:

    async def test_public_files_are_served_and_private_files_need_their_owner (
        self, client: Client, app: App,
    ) -> None:

        owner, mine = await member(client, rand.hex(4))
        other, _    = await member(client, rand.hex(4))
        shared      = await client.post("/v1/files", files={ "file": ("Cat.PNG", PNG, "image/png") }, headers=owner)
        public      = shared.created().data()
        secret      = { "file": ("secret.txt", b"top", "text/plain") }
        hidden      = (await client.post("/v1/files/private", files=secret, headers=owner)).created().data()

        try:

            expect(public).subset({ "mime": "image/png" })
            expect(public["url"]).starts_with("/storage/uploads/")
            expect(hidden["url"]).none()
            expect(hidden["path"]).starts_with(f"users/{mine}/")

            served = (await client.get(public["url"])).ok().header("content-type", "image/png")
            opened = (await client.get(f"/v1/files/{hidden['path']}", headers=owner)).ok()

            expect((served.content, opened.content)).equals((PNG, b"top"))
            expect(opened.headers["content-type"]).starts_with("text/plain")

            (await client.get(f"/storage/{hidden['path']}")).status(404)
            (await client.get(f"/v1/files/{hidden['path']}", headers=other)).fault(Code.NOT_FOUND, "fs.missing")
            (await client.get(f"/v1/files/{hidden['path']}")).fault(Code.UNAUTHORIZED)
            (await client.get(f"/v1/files/users/{mine}/..%2F..%2Fsecret.txt", headers=owner)).fault(
                Code.BAD_REQUEST, "storage.path",
            )
            (await client.post("/v1/files", headers=owner)).fault(Code.VALIDATION, field="file")
            (await client.post("/v1/files", files={ "file": ("a.txt", b"a", "text/plain") })).fault(Code.UNAUTHORIZED)
            (await client.post("/v1/files", files={ "file": ("x.php", b"<?php", "text/plain") }, headers=owner)).fault(
                Code.VALIDATION, field="file",
            )

        finally:

            await storage.delete(public["path"], "public")
            await storage.delete(hidden["path"], "private")

    def test_storage_paths_resolve_against_the_root_or_stay_absolute ( self, tmp_path: Path ) -> None:

        paths = StorageConfig(root="../shared", public="pub", private="/var/private", logs="logs")

        expect(paths.public_path(tmp_path / "api")).equals((tmp_path / "shared" / "pub").resolve())
        expect(paths.private_path(tmp_path / "api")).equals(Path("/var/private"))
        expect(paths.logs_path(tmp_path / "api")).equals((tmp_path / "shared" / "logs").resolve())
        expect(StorageConfig().public_path(tmp_path)).equals(tmp_path / "src" / "storage" / "app" / "public")
        expect(StorageConfig().assets_path(tmp_path)).equals(tmp_path / "src" / "public")
