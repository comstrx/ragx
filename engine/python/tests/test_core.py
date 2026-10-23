from datetime import UTC
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from engine.array import array
from engine.assets import Assets
from engine.cache import Cache
from engine.crypto import Crypto
from engine.date import Moment, Parser, date
from engine.error import Code, Fault, Faults
from engine.exception import Handler
from engine.fs import Bounds, fs
from engine.func import func
from engine.http import Envelope
from engine.json import json
from engine.net import Answer, Ask, Breaker, Client, net
from engine.rand import rand
from engine.string import string
from engine.test import expect, test
from engine.token import Claims, JwtAdapter, Token
from engine.validate import Email, Password, Shape, validate
from engine.parse import parse
from engine.thread import thread
from engine.view import View
import asyncio, hashlib, pytest

SECRET = "unit-secret-that-is-long-enough-for-hs256-ok"

class Signup(Shape):

    email    : Email
    password : Password

class Shade(Enum):

    DARK = "dark"

class TestPrimitives:

    @pytest.mark.anyio
    async def test_rules_patches_text_parsers_and_probes ( self ) -> None:

        data  = {
            "email": "Ann@Example.com", "age": "17", "password": "secret12", "password_confirmation": "secret12",
            "role": "admin", "tags": ["a"], "site": "https://x.test", "start": "2026-01-01", "end": "2025-12-31",
        }
        rules = {
            "email": "required|email|max:254", "age": "required|integer|min:18",
            "password": "required|string|min:8|confirmed", "role": "in:admin,client", "tags": "array|min:1",
            "site": "url", "start": "date|before:end", "nickname": "nullable|alpha_dash", "bio": "sometimes|string",
            "phone": "required_without:email",
        }
        doc: dict[str, Any] = { "a": { "b": [1, 2] }, "k": "v" }
        ops: list[dict[str, Any]] = [
            { "op": "add", "path": "/a/b/-", "value": 3 }, { "op": "replace", "path": "/k", "value": "w" },
            { "op": "move", "from": "/a/b/0", "path": "/first" }, { "op": "copy", "from": "/k", "path": "/again" },
            { "op": "test", "path": "/again", "value": "w" }, { "op": "remove", "path": "/a/b/0" },
        ]
        filled = { "flag": "yes", "code": "1234", "other": "" }
        hidden = { "password": "x", "nested": { "api_key": "y", "ok": 1 }, "list": [{ "token": "t" }] }

        expect(validate.make(data, rules)).equals({ "age": ["Must be at least 18"], "start": ["Must be before end"] })
        expect(validate.rules.passes({ "a": "x" }, { "a": "required|alpha" })).truthy()
        expect(validate.rules.fails({}, { "a": "required" })).truthy()
        expect(validate.make({ "n": 5 }, { "n": "bail|string|min:9" })).equals({ "n": ["Must be a string"] })
        expect(validate.make(filled, { "flag": "accepted", "code": "digits:4", "other": "filled" })).equals({
            "other": ["This field must not be empty"],
        })
        expect(validate.make({ "a": 1, "b": 2 }, { "b": "gt:a|different:a", "a": "lt:b|same:b" })).equals({
            "a": ["Must match b"],
        })
        expect(validate.make({ "n": "7" }, { "n": "numeric|between:1,5" })).equals({ "n": ["Must be between 1 and 5"] })
        expect(validate.make({}, { "n": "required" }, { "n.required": "Give n" })).equals({ "n": ["Give n"] })
        expect(validate.make({ "n": "x" }, { "n": "integer" }, { "integer": "Whole" })).equals({ "n": ["Whole"] })
        expect(validate.validated({ "x": "ok", "y": "ignored" }, { "x": "required" })).equals({ "x": "ok" })

        with test.fails(Code.VALIDATION, field="x") as refused: validate.validated({}, { "x": "required" })
        with test.fails(Code.INTERNAL, "validate.rule.nope"): validate.make({ "x": 1 }, { "x": "nope" })

        expect(test.some(refused.fault).errors).equals({ "x": ["This field is required"] })

        validate.extend("even", lambda c: None if int(c.value) % 2 == 0 else "Must be even")

        expect(validate.make({ "n": 3 }, { "n": "even" })).equals({ "n": ["Must be even"] })
        expect(validate.rules.names()).contains("even")

        patched = json.apply(doc, ops)

        expect(patched).equals({ "a": { "b": [3] }, "k": "w", "first": 1, "again": "w" })
        expect(doc["a"]["b"]).equals([1, 2])
        expect(json.pointer(patched, "/a/b/0")).equals(3)
        expect(json.pointer(patched, "/nope", 9)).equals(9)
        expect(json.has_pointer(patched, "/k")).truthy()
        expect(json.pointer_of("a", "x/y", 0)).equals("/a/x~1y/0")
        expect(json.changes({ "a": 1, "b": 2 }, { "a": 1, "b": 3, "c": 4 })).equals([
            { "op": "replace", "path": "/b", "value": 3 }, { "op": "add", "path": "/c", "value": 4 },
        ])
        expect(json.apply({ "a": 1, "b": 2 }, json.changes({ "a": 1, "b": 2 }, { "b": 3 }))).equals({ "b": 3 })
        expect(json.same({ "a": 1, "b": 2 }, { "b": 2, "a": 1 })).truthy()
        expect(len(json.checksum({}))).equals(32)
        expect(json.size({ "a": 1 })).equals(7)
        expect(json.redact(hidden)).equals({
            "password": "***", "nested": { "api_key": "***", "ok": 1 }, "list": [{ "token": "***" }],
        })

        with test.fails(Code.CONFLICT, "json.patch.test"): json.apply({}, [{ "op": "test", "path": "/x", "value": 1 }])
        with test.fails(Code.NOT_FOUND, "json.patch.path"):
            json.apply({}, [{ "op": "replace", "path": "/x", "value": 1 }])
        with test.fails(Code.BAD_REQUEST, "json.patch.op"): json.apply({}, [{ "op": "jump", "path": "/x" }])

        expect(parse.key_values("a=1, b = two,junk")).equals({ "a": "1", "b": "two" })
        expect(parse.csv_line('x, "y, z", 3')).equals(["x", "y, z", "3"])
        expect(parse.csv_rows("a,b\n1,2\n")).equals([["a", "b"], ["1", "2"]])
        expect(parse.tags("Go, go ,rust,,")).equals(["go", "rust"])
        expect(parse.ranges("1-3,7,10-8")).equals([1, 2, 3, 7, 10, 9, 8])
        expect(parse.semver("v1.2.3-rc.1+build5")).equals({
            "major": 1, "minor": 2, "patch": 3, "pre": "rc.1", "build": "build5",
        })
        expect(parse.semver("1.2")).none()
        expect(parse.version("v2.10.1-beta")).equals((2, 10, 1))
        expect(parse.compare_versions("1.10", "1.9")).equals(1)
        expect(parse.compare_versions("1.2.0", "1.2")).equals(0)
        expect(parse.satisfies("1.5", "1.0", "2.0")).truthy()
        expect(parse.satisfies("2.1", "1.0", "2.0")).falsy()
        expect(parse.numbers("x -1.5 and 2")).equals([-1.5, 2.0])
        expect(parse.words("hello, world_x!")).equals(["hello", "world", "x"])
        expect(parse.mentions("hi @ann and @bob.k, mail x@y")).equals(["ann", "bob.k"])
        expect(parse.hashtags("#go #rust")).equals(["go", "rust"])
        expect(parse.lines("a\n\n b \n")).equals(["a", " b"])
        expect(parse.flags(["--dry", "--name=x", "pos"])).equals({ "dry": True, "name": "x" })

        with test.fails(Code.BAD_REQUEST, "parse.ranges"): parse.ranges("a-b")

        port = net.free_port()

        expect(port).above(0)
        expect(await net.port_open("127.0.0.1", port, 0.5)).falsy()
        expect(await net.wait_port("127.0.0.1", port, within=0.2, every=0.05)).is_(False)

        def hang_up ( _reader: asyncio.StreamReader, writer: asyncio.StreamWriter ) -> None:

            writer.close()

        server = await asyncio.start_server(hang_up, "127.0.0.1", port)

        try:

            expect(await net.port_open("127.0.0.1", port)).truthy()
            expect(await net.wait_port("127.0.0.1", port, within=1)).truthy()

        finally:

            server.close()

            await server.wait_closed()

        expect(await net.resolve("localhost")).contains("127.0.0.1")
        expect(await net.resolve("nope.invalid")).equals([])
        expect(net.describe_host()["hostname"]).truthy()
        expect(net.local_ip()).truthy()

        await test.rejects(net.require_port("127.0.0.1", port, within=0.2), Code.UNAVAILABLE, "net.port")

    @pytest.mark.anyio
    async def test_files_archives_editors_phrases_regex_breakers_and_pages ( self, tmp_path: Path ) -> None:

        root   = tmp_path / "scan"
        cfg    = tmp_path / "app.env"
        text   = tmp_path / "t.txt"
        now    = Moment.of(2026, 10, 19, 9, 30)
        spoken = Parser()

        def when ( phrase: str ) -> Moment:

            return test.kind(spoken.parse(phrase, now, UTC), Moment)

        def before ( method: str, _url: str ) -> None:

            seen.append(("before", method))

        def failed ( _method: str, _url: str, fault: Fault ) -> None:

            seen.append(("error", fault.reason))
        seen: list[tuple[str, object]] = []
        times  = [0.0]

        def api ( asked: Ask ) -> Answer:

            if "/boom" in asked.url: return 503, json.encode({ "e": 1 }), { "content-type": "application/json" }

            page = int(net.query(asked.url).get("page", "1"))
            body = { "data": [page], "next": f"/items?page={page + 1}" if page < 3 else None }

            return 200, json.encode(body), { "content-type": "application/json" }

        (root / "a").mkdir(parents=True)
        (root / "empty").mkdir()

        await fs.write_text(root / "a" / "note.txt", "hello\nworld\n")
        await fs.write_bytes(root / "a" / "pic.png", b"\x89PNG")
        await fs.write_text(root / "zero.log", "")

        expect(fs.file.kind("x.png")).equals("image")
        expect(fs.file.kind("x.tar.gz")).equals("archive")
        expect(fs.file.kind("x.py")).equals("code")
        expect(fs.file.kind("x.pdf")).equals("document")
        expect(fs.file.kind("x.mp3")).equals("audio")
        expect(fs.file.kind("x.bin")).equals("executable")
        expect(fs.file.kind("x.xyz")).equals("other")
        expect(fs.file.is_image("a.jpg")).truthy()
        expect(fs.file.is_text("a.json")).truthy()
        expect(fs.file.is_media("a.mp4")).truthy()
        expect(fs.file.kinds()).contains("font")
        expect(fs.file.is_archive("a.zip")).truthy()

        grouped = await fs.dir.categorize(root)

        expect(sorted(grouped)).equals(["image", "other", "text"])
        expect(grouped["text"]).equals([root / "a" / "note.txt"])
        expect(await fs.dir.images(root)).equals([root / "a" / "pic.png"])
        expect(await fs.dir.empty_dirs(root)).equals([root / "empty"])
        expect(await fs.dir.empty_files(root)).equals([root / "zero.log"])
        expect(await fs.dir.depth(root)).equals(2)
        expect(await fs.dir.search(root, "note")).equals([root / "a" / "note.txt"])
        expect(await fs.dir.search(root, "world", names_only=False)).equals([root / "a" / "note.txt"])
        expect((await fs.dir.summary(root))["files"]).equals(3)
        expect((await fs.dir.disk_usage(root))["total"]).above(0)
        expect(await fs.dir.select(root, lambda path: path.suffix == ".png")).equals([root / "a" / "pic.png"])

        archive = await fs.archive.zip(tmp_path / "out" / "bundle.zip", root / "a")

        expect(await fs.archive.members(archive)).equals(["a/note.txt", "a/pic.png"])

        extracted = await fs.archive.extract(archive, tmp_path / "unz")

        expect(sorted(path.name for path in extracted)).equals(["note.txt", "pic.png"])
        expect(await fs.read_text(tmp_path / "unz" / "a" / "note.txt")).equals("hello\nworld\n")

        tarred = await fs.archive.compress(tmp_path / "out" / "bundle.tar.gz", root / "a" / "note.txt")

        expect(await fs.archive.members(tarred)).equals(["note.txt"])
        expect(fs.archive.is_archive(tarred)).truthy()
        expect(fs.archive.is_archive("x.txt")).falsy()
        expect(len(await fs.archive.untar(tarred, tmp_path / "unt"))).equals(1)

        await test.rejects(fs.archive.extract(tmp_path / "nope.rar", tmp_path), Code.BAD_REQUEST, "archive.kind")

        await fs.write_bytes(tmp_path / "bomb" / "zeros.bin", bytes(20 << 20))

        bombs = [
            await fs.archive.zip(tmp_path / "out" / "bomb.zip", tmp_path / "bomb" / "zeros.bin"),
            await fs.archive.compress(tmp_path / "out" / "bomb.tar.gz", tmp_path / "bomb" / "zeros.bin"),
        ]

        for bomb in bombs:

            await test.rejects(fs.archive.extract(bomb, tmp_path / "boom"), Code.BAD_REQUEST, "archive.bomb")

            expect((tmp_path / "boom").exists()).falsy()

        crowded = fs.archive.extract(archive, tmp_path / "few", Bounds(members=1))

        await test.rejects(crowded, Code.BAD_REQUEST, "archive.bomb")

        expect(len(await fs.archive.extract(bombs[0], tmp_path / "ok", Bounds(ratio=1e9)))).equals(1)

        await fs.write_text(cfg, "# head\nA=1\nexport B='two words'\n")

        expect(fs.editor.env_to_dict(await fs.read_text(cfg))).equals({ "A": "1", "B": "two words" })

        await fs.editor.env_set(cfg, "A", 2)
        await fs.editor.env_set(cfg, "C", "x y")

        expect(await fs.editor.env_get(cfg, "A")).equals("2")
        expect(await fs.editor.env_get(cfg, "C")).equals("x y")
        expect(await fs.editor.env_get(cfg, "Z", "d")).equals("d")
        expect(await fs.editor.env_delete(cfg, "B")).equals(1)
        expect(await fs.read_text(cfg)).lacks("B=")
        expect(fs.editor.dict_to_env({ "K": "v", "S": "a b" })).equals("K=v\nS='a b'\n")

        await fs.editor.env_merge(cfg, { "D": 4 })
        await fs.write_text(text, "one\ntwo\nthree\n")

        expect((await fs.editor.env_load(cfg))["D"]).equals("4")
        expect(await fs.editor.insert_after(text, "one", "1.5")).truthy()
        expect(await fs.editor.insert_before(text, "three", "2.5")).truthy()
        expect(await fs.editor.insert_after(text, "zzz", "x")).falsy()
        expect(await fs.editor.lines(text)).equals(["one", "1.5", "two", "2.5", "three"])
        expect(await fs.editor.delete_lines(text, lambda line: "." in line)).equals(2)

        await fs.editor.replace_line(text, 2, "TWO")
        await fs.editor.insert_line(text, 1, "zero")

        expect(await fs.editor.lines(text)).equals(["zero", "one", "TWO", "three"])
        expect(await fs.editor.ensure_line(text, "four")).truthy()
        expect(await fs.editor.ensure_line(text, "four")).falsy()

        await fs.write_text(text, "<a>old</a>")

        expect(await fs.editor.replace_between(text, "<a>", "</a>", "new")).truthy()
        expect(await fs.read_text(text)).equals("<a>new</a>")
        expect(fs.editor.extract_between("x[1]y", "[", "]")).equals("1")
        expect(fs.editor.extract_between("x", "[", "]")).none()

        await fs.editor.map_lines(text, str.upper)

        expect(await fs.read_text(text)).equals("<A>NEW</A>\n")

        await test.rejects(fs.editor.replace_line(text, 9, "x"), Code.BAD_REQUEST, "fs.line")

        backup = await fs.file.backup(text)

        expect(backup.name).equals("t.txt.bak")
        expect(await fs.exists(backup)).truthy()
        expect(set(await fs.file.times(text))).equals({ "created", "modified", "accessed" })

        await fs.file.chmod(text, 0o755)

        expect(await fs.file.is_runnable(text)).truthy()
        expect(await fs.file.is_runnable(tmp_path / "nope")).falsy()

        expect(string.search("order 42 shipped", r"\d+")).equals("42")
        expect(string.fullmatch("abc", r"[a-c]+")).truthy()
        expect(string.fullmatch("abcd", r"[a-c]+")).falsy()
        expect(string.sub("a1b2", r"\d", "#")).equals("a#b#")
        expect(string.groups("2026-10-18", r"(?P<y>\d{4})-(?P<m>\d{2})")).equals({ "y": "2026", "m": "10" })
        expect(string.split_regex("a, b;c", r"[,;]\s*")).equals(["a", "b", "c"])
        expect(string.escape("a.b")).equals("a\\.b")
        expect(string.equals_ignore_case("Straße", "STRASSE")).truthy()
        expect(string.replace_insensitive("Hello hello", "hello", "bye")).equals("bye bye")
        expect(string.strip_symbols("a-b, c!")).equals("ab c")
        expect(string.char_count("a b", spaces=False)).equals(2)
        expect(string.hash("x", size=8)).equals("2d711642")
        expect(string.title_safe("the lord of the rings")).equals("The Lord of the Rings")
        expect(string.preserve_case("Hello", "world")).equals("World")
        expect(string.preserve_case("HI", "yo")).equals("YO")

        expect(when("next friday").to_date_string()).equals("2026-10-23")
        expect(when("in 3 days").at.day).equals(22)
        expect(when("2 hours ago").at.hour).equals(7)
        expect(when("an hour from now").at.hour).equals(10)
        expect(when("last monday").at.day).equals(12)
        expect(when("this month").at.day).equals(1)
        expect(when("next month").month()).equals(11)
        expect(when("last year").year()).equals(2025)
        expect(when("end of day").at.hour).equals(23)
        expect(when("start of week").at.day).equals(19)
        expect(when("end of tomorrow").at.day).equals(20)
        expect(when("tomorrow at 3pm").at.hour).equals(15)
        expect(when("friday noon").at.hour).equals(12)
        expect(when("friday noon").at.day).equals(23)
        expect(when("25 december 2026").month()).equals(12)
        expect(when("14/07/2026").at.day).equals(14)
        expect(spoken.parse("gibberish", now, UTC)).none()
        expect(when("at 10:15").at.minute).equals(15)
        expect(when("at 10:15").at.day).equals(19)
        expect(when("monday").at.day).equals(19)
        expect(when("next quarter").month()).equals(1)
        expect(Moment.parse("next monday").at.weekday()).equals(0)
        expect(date.is_valid("in 2 weeks")).truthy()
        expect(date.parse("yesterday")).below(date.now())

        with test.fails(Code.BAD_REQUEST, "date.parse"): Moment.parse("the day after the flood")

        fuse   = Breaker("api", failures=2, reset=60)
        client = Client("http://api.test", transport=net.mocked(api), breaker=fuse)

        client.on_before(before).on_after(lambda reply: seen.append(("after", reply.status))).on_error(failed)

        expect([item async for item in client.pages("/items")]).equals([1, 2, 3])
        expect(seen[0]).equals(("before", "GET"))
        expect(seen[1]).equals(("after", 200))
        expect((await client.get("/boom")).status).equals(503)
        expect((await client.get("/boom")).status).equals(503)

        await test.rejects(client.get("/items"), Code.UNAVAILABLE, "breaker.api")

        held = client.breaker()

        held = test.some(held)
        expect(held.state).equals("open")
        expect(held.trips).equals(1)
        expect(client.with_bearer("t").with_basic("u", "p").with_header("X-A", "1")).is_(client)

        breaker = Breaker("x", failures=1, reset=10, clock=lambda: times[0])

        breaker.fail()

        expect(breaker.allow()).falsy()
        expect(breaker.is_open()).truthy()

        times[0] = 11.0

        expect(breaker.allow()).truthy()
        expect(breaker.state).equals("half_open")

        breaker.fail()

        expect(breaker.state).equals("open")
        expect(breaker.trips).equals(2)

        breaker.succeed()

        expect(breaker.state).equals("closed")
        expect(breaker.describe()["trips"]).equals(2)

        breaker.force_open()

        with test.fails(Code.UNAVAILABLE, "breaker.x"): breaker.guard()

        expect(await thread.compute(pow, 2, 10)).equals(1024)
        expect(array.reduce([1, 2, 3], lambda total, item: total + item, 0)).equals(6)

        thread.shutdown_processes()

        await client.close()

class TestConfig:

    def test_json_encodes_rich_values_and_digs_into_documents ( self ) -> None:

        document = { "d": Decimal("1.50"), "k": Shade.DARK, "s": { 2, 1 }, "b": b"hi", "n": { "m": [10, { "x": 1 }] } }
        encoded  = json.dumps(document, sort=True)

        expect(encoded).equals('{"b":"hi","d":"1.50","k":"dark","n":{"m":[10,{"x":1}]},"s":[1,2]}')
        expect(json.loads(encoded)["n"]["m"][1]).equals({ "x": 1 })
        expect(json.pretty({ "a": 1 })).equals('{\n  "a": 1\n}')
        expect(json.parse("{bad", "fallback")).equals("fallback")
        expect(json.parse(b"[1]")).equals([1])
        expect(json.parse(5)).none()
        expect(json.valid('{"a":1}')).truthy()
        expect(json.valid("{a}")).falsy()
        expect(json.looks(" [1]")).truthy()
        expect(json.looks("12")).falsy()
        expect(json.dig(document, "n.m.1.x")).equals(1)
        expect(json.dig(document, "n.m.-1.x")).equals(1)
        expect(json.dig(document, "n.q", 0)).equals(0)
        expect(json.flatten({ "a": { "b": { "c": 1 } }, "d": 2 })).equals({ "a.b.c": 1, "d": 2 })
        expect(json.clone(document)["d"]).equals("1.50")
        expect(json.dumps(object(), lenient=True)).starts_with('"<object')

        with test.raises(TypeError): json.dumps(object())
        with test.fails(Code.BAD_REQUEST): json.loads("{nope")

class TestFunc:

    @pytest.mark.anyio
    async def test_combinators_wrap_sync_and_async_alike ( self ) -> None:

        def triple ( left: int, middle: int, right: int ) -> int:

            return left + middle + right

        expect(func.curry(triple)(1)(2)(3)).equals(6)
        expect(func.curry(triple)(1, 2)(3)).equals(6)
        expect(func.curry(triple, 3)(1)(2, 3)).equals(6)
        expect(func.juxt(len, str.upper)("ab")).equals([2, "AB"])
        expect(func.unary(int)("7")).equals(7)

        later = func.after(2, lambda: "go")
        early = func.before(3, lambda n: n * 2)

        expect(later()).none()
        expect(later()).equals("go")
        expect([early(1), early(2), early(3)]).equals([2, 4, 4])

        expect(func.load("engine.string:string")).is_(string)
        expect(func.load("engine.rand").rand).is_(rand)
        expect(any(value is Handler for value in func.discover("engine.exception", callable))).truthy()

        calls: list[str] = []
        tries: list[str] = []
        seen: list[tuple[str, float]] = []

        def flaky () -> str:

            tries.append("try")

            if len(tries) < 3: raise OSError("not yet")

            return "done"

        async def slow () -> str:

            await asyncio.sleep(0.2)

            return "late"

        async def doubled ( number: int ) -> int:

            return number * 2

        def add ( left: int, right: int ) -> int:

            calls.append(f"memo:{left}:{right}")

            return left + right

        counted = func.once(calls.append)
        memo    = func.memo(add, ttl=60)

        counted("once")
        counted("twice")

        expect((memo(1, 2), memo(1, 2), memo(2, 2))).equals((3, 3, 4))
        expect(calls).equals(["once", "memo:1:2", "memo:2:2"])
        expect(func.pipe(lambda n: n + 1, lambda n: n * 2)(3)).equals(8)
        expect(func.safe(lambda: 1 // 0, default=-1)()).equals(-1)
        expect(func.retry(flaky, times=3, delay=0)()).equals("done")
        expect(len(tries)).equals(3)
        expect(await func.call(doubled, 4)).equals(8)
        expect(await func.call(len, "abc")).equals(3)
        expect(await func.measure(doubled, lambda name, ms: seen.append((name, ms)))(5)).equals(10)
        expect(seen[0][0]).ends_with("doubled")
        expect(seen[0][1] >= 0).true()
        expect(func.is_async(slow)).truthy()
        expect(func.is_async(flaky)).falsy()

        timed = await test.rejects(func.timeout(slow, 0.01)(), Code.UNAVAILABLE, "timeout")

        expect(timed.unknown).true()

        with test.fails(Code.INTERNAL, "retry.times"): func.retry(flaky, times=0)

class TestSecurity:

    def test_crypto_hashes_seals_rotates_and_refuses_garbage ( self ) -> None:

        crypto = Crypto()
        hashed = crypto.hash("hunter22")

        expect(hashed).starts_with("$argon2id$")
        expect(crypto.verify("hunter22", hashed)).truthy()
        expect(crypto.verify("x", hashed)).falsy()
        expect(crypto.stale(hashed)).falsy()
        expect(crypto.verify("hunter22", "not-a-hash")).falsy()

        with test.fails(Code.INTERNAL, "crypto"): crypto.seal("x")

        old, new = crypto.key(), crypto.key()

        crypto.setup([old])

        sealed = crypto.seal("payload")

        crypto.setup([new, old])

        expect(crypto.open_text(sealed)).equals("payload")
        expect(crypto.open_text(crypto.rotate(sealed))).equals("payload")
        expect(crypto.rotate(sealed)).differs(sealed)
        expect(crypto.digest("a")).equals(hashlib.sha256(b"a").hexdigest())
        expect(crypto.digest(b"a", "sha512")).differs(crypto.digest("a"))
        expect(crypto.sign("a", "k") == crypto.sign("a", "k") != crypto.sign("a", "j")).true()
        expect(crypto.compare("abc", "abc")).truthy()
        expect(crypto.compare("abc", "abx")).falsy()

        with test.fails(Code.BAD_REQUEST, "cipher"): crypto.open("garbage")

    @pytest.mark.anyio
    async def test_files_seal_and_open_with_the_rotating_keys ( self, tmp_path: Path ) -> None:

        vault = Crypto()

        vault.setup([vault.key()])

        await fs.write_text(tmp_path / "secret.txt", "top secret")

        sealed = await vault.seal_file(tmp_path / "secret.txt")
        opened = await vault.open_file(sealed, tmp_path / "back.txt")

        expect(sealed.name).equals("secret.txt.sealed")
        expect(await fs.read_text(opened)).equals("top secret")
        expect(vault.is_sealed(await fs.read_text(sealed))).truthy()
        expect(vault.is_sealed("plain")).falsy()

    def test_tokens_bind_subject_kind_issuer_and_expiry ( self ) -> None:

        token = Token()

        expect(token.ready()).falsy()

        token.setup(JwtAdapter(SECRET, issuer="unit"))

        text, claims = token.issue("user-1", "access", 60, roles=["admin"], sub="spoofed")
        verified     = token.verify(text, kind="access")
        past         = date.add(date.now(), minutes=-2)
        expired      = Claims("user-1", "access", "jti", past, date.add(past, minutes=1), {})
        stranger     = Token()

        stranger.setup(JwtAdapter(SECRET, issuer="other"))

        expect((verified.subject, verified.kind, verified.id)).equals(("user-1", "access", claims.id))
        expect(verified.extra["roles"]).equals(["admin"])
        expect(verified.extra).lacks("sub")
        expect(verified.alive()).truthy()
        expect(0 < verified.remaining() <= 60).true()
        expect(token.bearer("Bearer  abc ")).equals("abc")
        expect(token.basic("Basic a2V5OnNlY3JldDp3aXRoOmNvbG9ucw==")).equals(("key", "secret:with:colons"))

        for broken, reason in (
            (lambda: token.verify(text, kind="refresh"), "token.kind"),
            (lambda: token.verify(text[:-2] + "xx"), "token"),
            (lambda: token.verify(JwtAdapter(SECRET, issuer="unit").issue(expired)), "token.expired"),
            (lambda: stranger.verify(text), "token"),
            (lambda: token.bearer("Basic abc"), "token.missing"),
            (lambda: token.bearer(None), "token.missing"),
            (lambda: token.basic("Bearer a2V5OnNlY3JldA=="), "token.basic"),
            (lambda: token.basic("Basic not*base64"), "token.basic"),
            (lambda: token.basic("Basic a2V5"), "token.basic"),
            (lambda: token.basic("Basic OnNlY3JldA=="), "token.basic"),
            (lambda: token.basic(None), "token.basic"),
        ):

            with test.fails(Code.UNAUTHORIZED, reason): broken()

        with test.fails(Code.INTERNAL, "token.ttl"): token.issue("u", ttl=0)
        with test.fails(Code.INTERNAL, "token.secret"): JwtAdapter("short")

    def test_validation_normalizes_and_reports_per_field ( self ) -> None:

        expect(validate.check(Email, "  Foo@Bar.com ")).equals("foo@bar.com")
        expect(validate.passes(Password, "longenough")).truthy()
        expect(validate.passes(Password, "short")).falsy()
        expect(validate.is_email("a@b.co")).truthy()
        expect(validate.is_email("a@b")).falsy()
        expect(validate.is_uuid(str(rand.uuid()))).truthy()
        expect(validate.model(Signup, { "email": "A@B.CO", "password": "12345678" }).email).equals("a@b.co")
        expect(validate.one_of("a", ("a", "b"))).equals("a")

        with test.fails(Code.VALIDATION, field="password") as single: validate.check(Password, "short", "password")
        with test.fails(Code.VALIDATION) as many: validate.model(Signup, { "email": "nope", "password": "x" })
        with test.fails(Code.VALIDATION, field="kind") as choice: validate.one_of("z", ("a", "b"), "kind")

        expect(list(test.some(single.fault).errors or {})).equals(["password"])
        expect(sorted(test.some(many.fault).errors or {})).equals(["email", "password"])
        expect((test.some(choice.fault).errors or {})["kind"]).equals(["Choose one of: a, b"])

    def test_faults_and_envelopes_carry_code_status_reason_and_errors ( self ) -> None:

        fault = Faults().validation({ "name": ["required"] }, reason="body")
        plain = Fault(Code.CONFLICT)
        body  = Envelope.failure(fault, { "extra": 1 })

        expect((fault.status, fault.code, fault.reason)).equals((422, Code.VALIDATION, "body"))
        expect(fault.message).equals(Code.VALIDATION.message())
        expect((plain.status, plain.reason, plain.errors)).equals((409, None, None))
        expect((Code.of(404), Code.of(418), Code.of(503))).equals((Code.NOT_FOUND, Code.BAD_REQUEST, Code.UNAVAILABLE))
        expect(sorted(body)).equals(["code", "data", "errors", "message", "meta", "reason"])
        expect(body["errors"]).equals({ "name": ["required"] })
        expect(body["meta"]).equals({ "request_id": None, "extra": 1 })

@pytest.mark.anyio
class TestServices:

    async def test_cache_counts_remembers_and_limits_within_a_window ( self ) -> None:

        cache = Cache()
        loads: list[int] = []

        async def load () -> int:

            loads.append(1)

            return 42

        await cache.set("k", { "v": 1 }, ttl=60)

        expect(await cache.get("k")).equals({ "v": 1 })
        expect(await cache.has("k")).truthy()
        expect(await cache.get("missing", 0)).equals(0)
        expect(await cache.remember("r", 60, load)).equals(42)
        expect(await cache.remember("r", 60, load)).equals(42)
        expect(len(loads)).equals(1)
        expect(await cache.increment("n", 2)).equals(2)
        expect(await cache.increment("n")).equals(3)
        expect(await cache.forget("k")).truthy()
        expect(await cache.has("k")).falsy()
        expect(await cache.forget("k")).falsy()

        hits = [await cache.hit("bucket", 2, 60) for _ in range(3)]

        expect([hit.allowed for hit in hits]).equals([True, True, False])
        expect([hit.remaining for hit in hits]).equals([1, 0, 0])
        expect(0 < hits[2].reset <= 60).true()

    async def test_views_render_with_shared_data_filters_and_autoescape ( self, tmp_path: Path ) -> None:

        view = View()

        (tmp_path / "hi.html").write_text("{{ app }}: {{ name }} / {{ title|slug }} / {{ 'x y'|title_case }}\n")

        expect(view.ready()).falsy()
        expect(view.exists("hi.html")).falsy()

        statics = Assets()

        statics.setup(tmp_path, "/static")
        view.setup(tmp_path, { "app": "Unit", "assets": statics.url })

        expect(view.ready()).truthy()
        expect(view.exists("hi.html")).truthy()
        expect(view.exists("nope.html")).falsy()
        expect(view.folder()).equals(tmp_path)
        rendered = await view.render("hi.html", name="<b>A</b>", title="A B")

        expect(rendered).equals("Unit: &lt;b&gt;A&lt;/b&gt; / a-b / X Y")
        expect(await view.text("{{ 2500|human }} {{ 1|percent(4) }}")).equals("2.5K 25.0")
        expect(await view.text("{{ assets('hi.html') }}")).starts_with("/static/hi.html?v=")

        await test.rejects(view.render("nope.html"), Code.INTERNAL, "view.nope.html")

    async def test_assets_resolve_version_and_confine_public_files ( self, tmp_path: Path ) -> None:

        statics = Assets()

        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "logo.svg").write_text("<svg/>")
        (tmp_path / ".secret").write_text("hidden")

        statics.setup(tmp_path, "/static", "https://api.test")

        stamp = statics.stamp("images/logo.svg")

        expect(statics.ready()).truthy()
        expect(statics.prefix()).equals("/static")
        stamp = test.some(stamp)
        expect(len(stamp)).equals(10)
        expect(statics.url("images/logo.svg")).equals(f"https://api.test/static/images/logo.svg?v={stamp}")
        expect(statics.url("/images//logo.svg", absolute=False)).equals(f"/static/images/logo.svg?v={stamp}")
        expect(statics.url("missing.css")).equals("https://api.test/static/missing.css")
        expect(statics.exists("missing.css")).falsy()
        expect(statics.mime("images/logo.svg")).equals("image/svg+xml")
        expect(await statics.text("images/logo.svg")).equals("<svg/>")
        expect(await statics.list()).equals(["images/logo.svg"])

        (tmp_path / "images" / "logo.svg").write_text("<svg>2</svg>")

        expect(statics.stamp("images/logo.svg")).equals(stamp)

        statics.forget()

        expect(statics.stamp("images/logo.svg")).differs(stamp)

        for bad in ("../etc/passwd", ".secret", "images/../.secret", ""):

            with test.fails(Code.BAD_REQUEST, "assets.path"): statics.url(bad)

        await test.rejects(statics.read("missing.css"), Code.NOT_FOUND, "assets.missing")

    async def test_fs_writes_atomically_and_net_builds_urls ( self, tmp_path: Path ) -> None:

        target = tmp_path / "deep" / "data.json"
        notes  = tmp_path / "notes.txt"

        await fs.write_json(target, { "a": [1, 2] })
        await fs.write_text(notes, "one\n")
        await fs.append(notes, "two\n")

        expect(await fs.read_json(target)).equals({ "a": [1, 2] })
        expect(await fs.read_text(notes)).equals("one\ntwo\n")
        expect(await fs.exists(target)).truthy()
        expect(await fs.is_dir(target.parent)).truthy()
        expect(await fs.size(notes)).equals(8)
        expect([path.name for path in await fs.list(tmp_path, "*.txt")]).equals(["notes.txt"])
        expect([path.name for path in await fs.list(tmp_path)]).equals(["deep", "notes.txt"])
        copied = await fs.copy(notes, tmp_path / "copy.txt")
        moved  = await fs.move(copied, tmp_path / "moved.txt")

        expect(await fs.read_text(moved)).equals("one\ntwo\n")
        expect(await fs.exists(copied)).falsy()
        expect(await fs.remove(notes)).truthy()
        expect(await fs.remove(notes)).falsy()
        expect(fs.within(tmp_path, target)).truthy()
        expect(fs.within(tmp_path, tmp_path / ".." / "escape")).falsy()
        expect((fs.name(target), fs.stem(target), fs.extension(target))).equals(("data.json", "data", "json"))

        origin = fs.drivers.local("origin", tmp_path / "origin", "/o")
        mirror = fs.drivers.local("mirror", tmp_path / "mirror")

        expect(await origin.put("a/one.txt", b"1", "text/plain")).equals(1)
        expect(await origin.upload(moved, "b/moved.txt")).equals(8)
        expect(await origin.sync(mirror)).equals(2)
        expect(await mirror.list()).equals(["a/one.txt", "b/moved.txt"])
        expect(await origin.sync(mirror)).equals(0)
        expect(origin.url("a/one.txt")).equals("/o/a/one.txt")
        expect(mirror.public()).falsy()
        expect(await mirror.download("b/moved.txt", tmp_path / "back.txt")).equals(8)
        expect(await fs.read_text(tmp_path / "back.txt")).equals("one\ntwo\n")
        expect(await mirror.delete("a/one.txt")).truthy()
        expect(await mirror.exists("a/one.txt")).falsy()
        expect(await mirror.delete("a/one.txt")).falsy()
        expect(fs.drivers.has("mirror")).truthy()
        expect({ "mirror", "origin" } <= set(fs.drivers.names())).true()
        expect(fs.use("origin")).is_(origin)
        expect(await fs.drivers.sync("origin", "mirror")).equals(1)
        expect(fs.drivers.forget("origin")).truthy()
        expect(fs.drivers.forget("mirror")).truthy()
        expect(fs.drivers.describe()["drivers"]).lacks("origin")

        with test.fails(Code.INTERNAL, "fs.origin.missing"): fs.drivers.use("origin")

        url = net.url("https://api.x.test/", "v1", "/users/", q="a b", page=2)

        expect(url).equals("https://api.x.test/v1/users?q=a+b&page=2")
        expect(net.query(url)).equals({ "q": "a b", "page": "2" })
        expect(net.host(url)).equals("api.x.test")
        expect(net.origin(url)).equals("https://api.x.test")
        expect(net.origin("nope")).equals("")
        expect(net.is_url(url)).truthy()
        expect(net.is_url("ftp://x")).falsy()
        expect(net.is_ip("10.0.0.1")).truthy()
        expect(net.is_ip("10.0.0")).falsy()
