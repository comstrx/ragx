from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from core.error import Code
from core.fs import LocalDriver
from core.net import Answer, Ask, Egress, net
from core.storage import Storage
from core.test import expect, test
import asyncio

PUBLIC  = "93.184.216.34"
PAYLOAD = b"remote bytes"

async def public ( host: str, port: int ) -> Sequence[str]:

    return [PUBLIC]

async def rebound ( host: str, port: int ) -> Sequence[str]:

    return [PUBLIC, "10.0.0.7"]

async def metadata ( host: str, port: int ) -> Sequence[str]:

    return ["169.254.169.254"] if host == "metadata.internal" else [PUBLIC]

@asynccontextmanager
async def served () -> AsyncIterator[tuple[int, list[int]]]:

    hits: list[int] = []

    async def answer ( reader: asyncio.StreamReader, writer: asyncio.StreamWriter ) -> None:

        hits.append(1)

        await reader.readuntil(b"\r\n\r\n")

        writer.write(b"HTTP/1.1 200 OK\r\ncontent-length: %d\r\nconnection: close\r\n\r\n" % len(PAYLOAD) + PAYLOAD)

        await writer.drain()

        writer.close()

    server = await asyncio.start_server(answer, "127.0.0.1", 0)

    try: yield server.sockets[0].getsockname()[1], hits
    finally:

        server.close()

        await server.wait_closed()

class TestEgress:

    def test_only_public_addresses_pass_and_private_never_opens_metadata ( self ) -> None:

        strict  = Egress()
        private = Egress(private=True)

        for address in ("93.184.216.34", "2606:4700:4700::1111"):

            expect(strict.allows(address)).truthy()

        for address in (
            "10.0.0.1", "127.0.0.1", "::1", "::ffff:127.0.0.1", "169.254.169.254", "fe80::1", "100.64.0.1",
            "::", "224.0.0.1", "192.168.1.10", "fd00::1", "not-an-ip",
        ):

            expect(strict.allows(address)).falsy()

        expect([private.allows(address) for address in ("10.0.0.1", "127.0.0.1", "::1")]).each(bool)
        expect([private.allows(address) for address in ("169.254.169.254", "fe80::1", "224.0.0.1")]).equals(
            [False, False, False],
        )

    async def test_urls_are_refused_by_scheme_credentials_host_and_port_before_any_lookup ( self ) -> None:

        seen: list[Ask] = []

        def answer ( asked: Ask ) -> Answer:

            seen.append(asked)

            return 200, PAYLOAD, {}

        listed = Egress.of(hosts=("files.example",))

        for policy, url, reason in (
            (Egress(), "http://files.example/a.png", "net.egress.scheme"),
            (Egress(), "https://user:secret@files.example/a.png", "net.egress.url"),
            (listed, "https://other.example/a.png", "net.egress.host"),
            (Egress(), "https://files.example:6379/a.png", "net.egress.port"),
        ):

            client = policy.client(transport=net.mocked(answer), resolver=public)

            await test.rejects(client.get(url), Code.FORBIDDEN, reason)
            await client.close()

        expect(seen).equals([])

    async def test_requests_are_pinned_to_the_checked_address_and_redirects_are_checked_again ( self ) -> None:

        seen: list[Ask] = []

        def answer ( asked: Ask ) -> Answer:

            seen.append(asked)

            if asked.url.endswith("/hop"): return 302, b"", { "location": "https://metadata.internal/latest/meta-data" }

            return 200, PAYLOAD, {}

        client = Egress().client(transport=net.mocked(answer), resolver=metadata)
        found  = await client.get("https://files.example/a.png")

        expect((found.status, found.body)).equals((200, PAYLOAD))
        expect((seen[0].url, seen[0].headers["host"])).equals((f"https://{PUBLIC}/a.png", "files.example"))

        await test.rejects(client.get("https://files.example/hop"), Code.FORBIDDEN, "net.egress.address")

        expect([asked.url for asked in seen]).equals([f"https://{PUBLIC}/a.png", f"https://{PUBLIC}/hop"])

        await client.close()

        rebinding = Egress().client(transport=net.mocked(answer), resolver=rebound)

        await test.rejects(rebinding.get("https://files.example/a.png"), Code.FORBIDDEN, "net.egress.address")
        await rebinding.close()

    async def test_real_sockets_reach_a_private_server_only_when_the_policy_says_so ( self, tmp_path: Path ) -> None:

        async with served() as (port, hits):

            opened = Egress.of(("http",), private=True)
            closed = Egress.of(("http",))
            ports  = frozenset({ port })
            inner  = Egress(opened.schemes, opened.hosts, ports, private=True).client()
            outer  = Egress(closed.schemes, closed.hosts, ports).client()

            expect((await inner.get(f"http://localhost:{port}/file.txt")).body).equals(PAYLOAD)

            await test.rejects(outer.get(f"http://localhost:{port}/file.txt"), Code.FORBIDDEN, "net.egress.address")
            await inner.close()
            await outer.close()

            store = Storage()

            store.setup({ "public": LocalDriver(tmp_path) })

            await test.rejects(store.fetch(f"http://127.0.0.1:{port}/x.txt"), Code.FORBIDDEN, "net.egress.scheme")

            store.setup({ "public": LocalDriver(tmp_path) }, egress=Egress(closed.schemes, ports=ports))

            await test.rejects(store.fetch(f"http://127.0.0.1:{port}/x.txt"), Code.FORBIDDEN, "net.egress.address")

            store.setup({ "public": LocalDriver(tmp_path) }, egress=Egress(closed.schemes, ports=ports, private=True))

            fetched = await store.fetch(f"http://127.0.0.1:{port}/x.txt", keep=True, pattern="")

            expect((fetched.path, await store.text(fetched.path), len(hits))).equals(
                ("downloads/x.txt", PAYLOAD.decode(), 2),
            )

    async def test_a_name_falls_through_to_its_next_checked_address_when_one_refuses ( self ) -> None:

        async def lookup ( host: str, port: int ) -> list[str]:

            return ["127.0.0.2", "127.0.0.1"]

        async with served() as (port, hits):

            policy = Egress.of(("http",), private=True)
            client = Egress(policy.schemes, policy.hosts, frozenset({ port }), private=True).client(resolver=lookup)

            expect((await client.get(f"http://service.test:{port}/file.txt")).body).equals(PAYLOAD)
            expect(len(hits)).equals(1)

            await client.close()
