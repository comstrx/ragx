from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from email.message import EmailMessage
from pathlib import Path
from typing import ClassVar

from core.array import array
from core.assets import Assets
from core.cache import Cache
from core.config import Config, Env, Settings
from core.crypto import Crypto
from core.date import date
from core.exceptions import Code, Fault, Faults, Handler
from core.fs import fs
from core.func import func
from core.http import Envelope
from core.json import json
from core.mail import Attachment, Mail, MemoryTransport, Message
from core.net import net
from core.number import number
from core.rand import rand
from core.string import string
from core.token import Claims, JwtAdapter, Token
from core.validate import Email, Password, validate
from core.value import value
from core.view import View
from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
import asyncio, hashlib, os, pytest

SECRET = "unit-secret-that-is-long-enough-for-hs256-ok"
SCRUB  = ("DEMO_NAME", "DEMO_PORT", "DEMO_TAGS", "DEMO_SECRET_KEY", "SHARED", "APP_ENV")

class Signup(BaseModel):

    email    : Email
    password : Password

class Demo(Settings):

    model_config = SettingsConfigDict(env_prefix="DEMO_")

    name  : str = "demo"
    port  : int = 1
    tags  : list[str] = Field(default_factory=list)

class Shade(Enum):

    DARK = "dark"

class TestPrimitives:

    def test_rand_is_strong_bounded_and_defaults_to_uuid7 ( self ) -> None:

        first, second = rand.uuid(), rand.uuid()
        start, end    = datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 12, 31, tzinfo=UTC)

        assert (first.version, second.version, rand.uuid(4).version) == (7, 7, 4)
        assert str(first) < str(second)
        assert rand.otp().isdigit() and len(rand.otp(4)) == 4
        assert len(rand.string(24)) == 24 and rand.string(8, "ab").strip("ab") == ""
        assert len(rand.hex(8)) == 16 and len(rand.bytes(9)) == 9 and len(rand.token()) >= 32
        assert all(3 <= rand.number(3, 5) <= 5 for _ in range(64))
        assert 0.0 <= rand.float() < 1.0 and rand.bool() in (True, False)
        assert rand.choice([7]) == 7 and len(rand.sample(range(10), 3)) == 3
        assert sorted(rand.shuffle([3, 1, 2])) == [1, 2, 3]
        assert start <= rand.date(start, end) <= end

        with pytest.raises(ValueError): rand.uuid(1)
        with pytest.raises(ValueError): rand.number(5, 3)
        with pytest.raises(ValueError): rand.date(end, start)

    def test_value_casts_are_lenient_on_input_and_strict_on_output ( self ) -> None:

        assert (value.bool("Yes"), value.bool("off"), value.bool(None), value.bool(2)) == (True, False, False, True)
        assert (value.integer("42"), value.integer("x", 7), value.integer("3.9"), value.integer(True)) == (42, 7, 3, 1)
        assert (value.float("2.50"), value.float("nope", 1.5), value.float("2.346", digits=2)) == (2.5, 1.5, 2.35)
        assert value.decimal("19.999") == Decimal("20.00") and value.positive("-3") == 0.0
        assert (value.string("  a "), value.string(None), value.string(True)) == ("a", None, "true")
        assert value.text(None) == ""
        assert (value.list("a, b"), value.list("[1, 2]")) == (["a", "b"], [1, 2])
        assert (value.list(None), value.list((1,))) == ([], [1])
        assert (value.dict('{"k": 1}'), value.dict("nope"), value.dict({ 1: 2 })) == ({ "k": 1 }, {}, { "1": 2 })
        assert (value.parse('"q"'), value.parse("12"), value.parse("{bad")) == ("q", "12", "{bad")
        assert value.empty("  ") and value.empty([]) and value.empty(False) and not value.empty(0)
        assert value.incoming({ "a": { "b": "[1]" } }, "a.b") == [1] and value.incoming({}, "a.b", "d") == "d"

    def test_string_array_number_and_date_helpers_agree_on_edges ( self ) -> None:

        now = date.now().replace(microsecond=123000)

        assert string.slug("Hello, World!") == "hello-world" and string.snake("HelloWorld") == "hello_world"
        assert string.from_base64(string.to_base64("héllo")) == "héllo".encode()
        assert string.from_base64(string.to_base64(b"\xff\x00", url=True).rstrip("="), url=True) == b"\xff\x00"
        assert (string.plural("city"), string.plural("box"), string.plural("cat", 1)) == ("cities", "boxes", "cat")
        assert (string.singular("cities"), string.singular("boxes")) == ("city", "box")
        assert string.singular("roles") == "role"
        assert array.page(45, 2, 20) == { "page": 2, "limit": 20, "total": 45, "pages": 3 }
        assert array.chunk([1, 2, 3], 2) == [[1, 2], [3]] and array.unique([1, 1, 2]) == [1, 2]
        assert array.group(["aa", "b", "cc"], len) == { 2: ["aa", "cc"], 1: ["b"] }
        assert array.from_base64(array.to_base64([255, 0, 7], url=True), url=True) == [255, 0, 7]
        assert (number.clamp(5, 0, 3), number.percent(1, 3)) == (3, 33.33)
        assert (number.pages(45, 20), number.human(1500)) == (3, "1.5K")
        assert date.parse(date.iso(now)) == now and date.iso(now).endswith("Z")
        assert date.add(now, days=1) - now == timedelta(days=1)
        assert date.between(now, date.add(now, minutes=-1), date.add(now, minutes=1))

        with pytest.raises(ValueError): string.from_base64("!!")

class TestConfig:

    def test_env_layers_files_by_mode_and_config_reads_dotted_keys ( self, tmp_path: Path ) -> None:

        (tmp_path / ".env").write_text("DEMO_NAME=base\nDEMO_PORT=10\nAPP_ENV=local\nSHARED=env\n")
        (tmp_path / ".env.local").write_text('DEMO_NAME=local\nDEMO_TAGS=["a","b"]\n')
        (tmp_path / ".env.production").write_text("DEMO_NAME=production\n")
        (tmp_path / ".env.prod").write_text("DEMO_PORT=443\n")
        (tmp_path / ".secret").write_text("DEMO_SECRET_KEY=hidden\n")

        for key in SCRUB: os.environ.pop(key, None)

        os.environ["SHARED"] = "process"

        env = Env()

        assert env.load(tmp_path) == "local"
        assert [path.name for path in env.loaded()] == [".env", ".env.local", ".secret"]
        assert (env.get("DEMO_NAME"), env.int("DEMO_PORT"), env.get("SHARED")) == ("local", 10, "process")
        assert env.list("DEMO_TAGS") == ["a", "b"] and env.get("DEMO_SECRET_KEY") == "hidden" and env.mode() == "local"

        config = Config()
        demo   = config.register("demo", Demo)

        assert (demo.name, demo.port, demo.tags) == ("local", 10, ["a", "b"])
        assert config.get("demo.name") == "local" and config.get("demo.missing", "d") == "d"
        assert config.names() == ["demo"]
        assert config.register("demo", Demo) is demo and config.of("demo", Demo) is demo

        config.set("demo.name", "override")

        assert config.get("demo.name") == "override" and config.all()["demo"]["name"] == "override"
        assert config.remove("demo.name") and not config.remove("demo.name") and config.get("demo.name") == "local"

        for key in SCRUB: os.environ.pop(key, None)

        production = Env()

        assert production.load(tmp_path, "production") == "production"
        assert [path.name for path in production.loaded()] == [".env", ".env.production", ".env.prod", ".secret"]
        assert (production.get("DEMO_NAME"), production.int("DEMO_PORT")) == ("production", 443)
        production.set("DEMO_PORT", 8)

        assert production.int("DEMO_PORT") == 8 and production.remove("DEMO_PORT")

        with pytest.raises(KeyError): production.require("DEMO_PORT")
        with pytest.raises(KeyError): config.require("demo.nothing")

        for key in SCRUB: os.environ.pop(key, None)

    def test_json_encodes_rich_values_and_digs_into_documents ( self ) -> None:

        document = { "d": Decimal("1.50"), "k": Shade.DARK, "s": { 2, 1 }, "b": b"hi", "n": { "m": [10, { "x": 1 }] } }
        encoded  = json.dumps(document, sort=True)

        assert encoded == '{"b":"hi","d":"1.50","k":"dark","n":{"m":[10,{"x":1}]},"s":[1,2]}'
        assert json.loads(encoded)["n"]["m"][1] == { "x": 1 } and json.pretty({ "a": 1 }) == '{\n  "a": 1\n}'
        assert json.parse("{bad", "fallback") == "fallback" and json.parse(b"[1]") == [1] and json.parse(5) is None
        assert json.valid('{"a":1}') and not json.valid("{a}") and json.looks(" [1]") and not json.looks("12")
        assert json.dig(document, "n.m.1.x") == 1 and json.dig(document, "n.m.-1.x") == 1
        assert json.dig(document, "n.q", 0) == 0
        assert json.flatten({ "a": { "b": { "c": 1 } }, "d": 2 }) == { "a.b.c": 1, "d": 2 }
        assert json.clone(document)["d"] == "1.50" and json.dumps(object(), lenient=True).startswith('"<object')

        with pytest.raises(TypeError): json.dumps(object())
        with pytest.raises(Fault): json.loads("{nope")

    def test_exception_handlers_map_report_and_never_leak ( self ) -> None:

        def located ( error: BaseException ) -> Fault:
            return Fault(Code.NOT_FOUND, reason=str(error))

        class Mapped(Handler):

            maps   : ClassVar[Mapping[type[BaseException], Code | Callable[[BaseException], Fault]]] = {
                ValueError: Code.BAD_REQUEST, LookupError: located,
            }
            silent : ClassVar[tuple[type[BaseException], ...]] = (KeyError,)

        handler = Mapped()

        assert handler.fault_of(ValueError("x")).code == Code.BAD_REQUEST
        assert handler.fault_of(KeyError("k")).reason == "'k'" and handler.fault_of(IndexError()).code == Code.NOT_FOUND
        assert handler.fault_of(RuntimeError("secret")).message == "Something went wrong"
        assert handler.handle(Fault(Code.FORBIDDEN, reason="nope")).reason == "nope"
        assert Handler().fault_of(ValueError("x")).code == Code.INTERNAL

class TestFunc:

    @pytest.mark.anyio
    async def test_combinators_wrap_sync_and_async_alike ( self ) -> None:

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

        assert (memo(1, 2), memo(1, 2), memo(2, 2)) == (3, 3, 4)
        assert calls == ["once", "memo:1:2", "memo:2:2"]
        assert func.pipe(lambda n: n + 1, lambda n: n * 2)(3) == 8
        assert func.safe(lambda: 1 // 0, default=-1)() == -1
        assert func.retry(flaky, times=3, delay=0)() == "done" and len(tries) == 3
        assert await func.call(doubled, 4) == 8 and await func.call(len, "abc") == 3
        assert await func.measure(doubled, lambda name, ms: seen.append((name, ms)))(5) == 10
        assert seen[0][0].endswith("doubled") and seen[0][1] >= 0
        assert func.is_async(slow) and not func.is_async(flaky)

        with pytest.raises(TimeoutError): await func.timeout(slow, 0.01)()
        with pytest.raises(ValueError): func.retry(flaky, times=0)

class TestSecurity:

    def test_crypto_hashes_seals_rotates_and_refuses_garbage ( self ) -> None:

        crypto = Crypto()
        hashed = crypto.hash("hunter22")

        assert hashed.startswith("$argon2id$") and crypto.verify("hunter22", hashed) and not crypto.verify("x", hashed)
        assert not crypto.stale(hashed) and not crypto.verify("hunter22", "not-a-hash")

        with pytest.raises(Fault) as unset: crypto.seal("x")

        assert unset.value.code == Code.INTERNAL

        old, new = crypto.key(), crypto.key()

        crypto.setup([old])

        sealed = crypto.seal("payload")

        crypto.setup([new, old])

        assert crypto.open_text(sealed) == "payload"
        assert crypto.open_text(crypto.rotate(sealed)) == "payload" and crypto.rotate(sealed) != sealed
        assert crypto.digest("a") == hashlib.sha256(b"a").hexdigest()
        assert crypto.digest(b"a", "sha512") != crypto.digest("a")
        assert crypto.sign("a", "k") == crypto.sign("a", "k") != crypto.sign("a", "j")
        assert crypto.compare("abc", "abc") and not crypto.compare("abc", "abx")

        with pytest.raises(Fault) as refused: crypto.open("garbage")

        assert refused.value.code == Code.BAD_REQUEST

    def test_tokens_bind_subject_kind_issuer_and_expiry ( self ) -> None:

        token = Token()

        assert not token.ready()

        token.setup(JwtAdapter(SECRET, issuer="unit"))

        text, claims = token.issue("user-1", "access", 60, roles=["admin"], sub="spoofed")
        verified     = token.verify(text, kind="access")
        past         = date.add(date.now(), minutes=-2)
        expired      = Claims("user-1", "access", "jti", past, date.add(past, minutes=1), {})
        stranger     = Token()

        stranger.setup(JwtAdapter(SECRET, issuer="other"))

        assert (verified.subject, verified.kind, verified.id) == ("user-1", "access", claims.id)
        assert verified.extra["roles"] == ["admin"] and "sub" not in verified.extra
        assert verified.alive() and 0 < verified.remaining() <= 60
        assert token.bearer("Bearer  abc ") == "abc"

        for broken, reason in (
            (lambda: token.verify(text, kind="refresh"), "token.kind"),
            (lambda: token.verify(text[:-2] + "xx"), "token"),
            (lambda: token.verify(JwtAdapter(SECRET, issuer="unit").issue(expired)), "token.expired"),
            (lambda: stranger.verify(text), "token"),
            (lambda: token.bearer("Basic abc"), "token.missing"),
            (lambda: token.bearer(None), "token.missing"),
        ):

            with pytest.raises(Fault) as caught: broken()

            assert (caught.value.code, caught.value.reason) == (Code.UNAUTHORIZED, reason)

        with pytest.raises(ValueError): token.issue("u", ttl=0)
        with pytest.raises(Fault): JwtAdapter("short")

    def test_validation_normalizes_and_reports_per_field ( self ) -> None:

        assert validate.check(Email, "  Foo@Bar.com ") == "foo@bar.com"
        assert validate.passes(Password, "longenough") and not validate.passes(Password, "short")
        assert validate.is_email("a@b.co") and not validate.is_email("a@b") and validate.is_uuid(str(rand.uuid()))
        assert validate.model(Signup, { "email": "A@B.CO", "password": "12345678" }).email == "a@b.co"
        assert validate.one_of("a", ("a", "b")) == "a"

        with pytest.raises(Fault) as single: validate.check(Password, "short", "password")
        with pytest.raises(Fault) as many: validate.model(Signup, { "email": "nope", "password": "x" })
        with pytest.raises(Fault) as choice: validate.one_of("z", ("a", "b"), "kind")

        assert single.value.code == Code.VALIDATION and list(single.value.errors or {}) == ["password"]
        assert sorted(many.value.errors or {}) == ["email", "password"]
        assert (choice.value.errors or {})["kind"] == ["Choose one of: a, b"]

    def test_faults_and_envelopes_carry_code_status_reason_and_errors ( self ) -> None:

        fault = Faults().validation({ "name": ["required"] }, reason="body")
        plain = Fault(Code.CONFLICT)
        body  = Envelope.failure(fault, { "extra": 1 })

        assert (fault.status, fault.code, fault.reason) == (422, Code.VALIDATION, "body")
        assert fault.message == Code.VALIDATION.message()
        assert (plain.status, plain.reason, plain.errors) == (409, None, None)
        assert (Code.of(404), Code.of(418), Code.of(503)) == (Code.NOT_FOUND, Code.BAD_REQUEST, Code.UNAVAILABLE)
        assert sorted(body) == ["code", "data", "errors", "message", "meta", "reason"]
        assert body["errors"] == { "name": ["required"] } and body["meta"] == { "request_id": None, "extra": 1 }

@pytest.mark.anyio
class TestServices:

    async def test_cache_counts_remembers_and_limits_within_a_window ( self ) -> None:

        cache = Cache()
        loads: list[int] = []

        async def load () -> int:

            loads.append(1)

            return 42

        await cache.set("k", { "v": 1 }, ttl=60)

        assert await cache.get("k") == { "v": 1 } and await cache.has("k") and await cache.get("missing", 0) == 0
        assert await cache.remember("r", 60, load) == 42 and await cache.remember("r", 60, load) == 42
        assert len(loads) == 1
        assert await cache.increment("n", 2) == 2 and await cache.increment("n") == 3
        assert await cache.forget("k") and not await cache.has("k") and not await cache.forget("k")

        hits = [await cache.hit("bucket", 2, 60) for _ in range(3)]

        assert [hit.allowed for hit in hits] == [True, True, False]
        assert [hit.remaining for hit in hits] == [1, 0, 0] and 0 < hits[2].reset <= 60

    async def test_views_render_with_shared_data_filters_and_autoescape ( self, tmp_path: Path ) -> None:

        view = View()

        (tmp_path / "hi.html").write_text("{{ app }}: {{ name }} / {{ title|slug }} / {{ 'x y'|title_case }}\n")

        assert not view.ready() and not view.exists("hi.html")

        statics = Assets()

        statics.setup(tmp_path, "/static")
        view.setup(tmp_path, { "app": "Unit", "assets": statics.url })

        assert view.ready() and view.exists("hi.html") and not view.exists("nope.html") and view.folder() == tmp_path
        assert await view.render("hi.html", name="<b>A</b>", title="A B") == "Unit: &lt;b&gt;A&lt;/b&gt; / a-b / X Y"
        assert await view.text("{{ 2500|human }} {{ 1|percent(4) }}") == "2.5K 25.0"
        assert (await view.text("{{ assets('hi.html') }}")).startswith("/static/hi.html?v=")

        with pytest.raises(Fault) as missing: await view.render("nope.html")

        assert missing.value.reason == "view.nope.html"

    async def test_mail_composes_multipart_messages_and_refuses_empty_ones ( self ) -> None:

        outbox = MemoryTransport()
        mail   = Mail()
        full   = Message(
            ("a@x.test",), "Hi", html="<p>Hi</p>", text="Hi", cc=("c@x.test",), bcc=("b@x.test",),
            reply_to="r@x.test", attachments=(Attachment("note.txt", b"note", "text/plain"),), headers={ "X-Tag": "t" },
        )

        with pytest.raises(Fault) as unset: await mail.send(full)
        with pytest.raises(Fault) as blank: mail.setup(outbox, "")

        assert (unset.value.reason, blank.value.reason) == ("mail", "mail.sender")

        mail.setup(outbox, "no-reply@x.test", "Unit")

        await mail.send(full)

        raw  = mail.compose(full, mail.sender())
        last = outbox.last()

        assert mail.sender() == "Unit <no-reply@x.test>" and mail.transport() is outbox
        assert last is full and full.recipients() == ("a@x.test", "c@x.test", "b@x.test")
        assert isinstance(raw, EmailMessage) and raw["To"] == "a@x.test"
        assert raw["Cc"] == "c@x.test" and raw["Bcc"] is None
        assert raw["Reply-To"] == "r@x.test" and raw["X-Tag"] == "t" and raw.get_body(("html",)) is not None
        assert [part.get_filename() for part in raw.iter_attachments()] == ["note.txt"]

        for broken, reason in (
            (Message((), "Hi", text="x"), "mail.to"),
            (Message(("a@x.test",), "Hi"), "mail.body"),
        ):

            with pytest.raises(Fault) as refused: await mail.send(broken)

            assert (refused.value.code, refused.value.reason) == (Code.BAD_REQUEST, reason)

        outbox.clear()

        assert outbox.last() is None

    async def test_assets_resolve_version_and_confine_public_files ( self, tmp_path: Path ) -> None:

        statics = Assets()

        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "logo.svg").write_text("<svg/>")
        (tmp_path / ".secret").write_text("hidden")

        statics.setup(tmp_path, "/static", "https://api.test")

        stamp = statics.stamp("images/logo.svg")

        assert statics.ready() and statics.prefix() == "/static" and stamp is not None and len(stamp) == 10
        assert statics.url("images/logo.svg") == f"https://api.test/static/images/logo.svg?v={stamp}"
        assert statics.url("/images//logo.svg", absolute=False) == f"/static/images/logo.svg?v={stamp}"
        assert statics.url("missing.css") == "https://api.test/static/missing.css" and not statics.exists("missing.css")
        assert statics.mime("images/logo.svg") == "image/svg+xml" and await statics.text("images/logo.svg") == "<svg/>"
        assert await statics.list() == ["images/logo.svg"]

        (tmp_path / "images" / "logo.svg").write_text("<svg>2</svg>")

        assert statics.stamp("images/logo.svg") == stamp

        statics.forget()

        assert statics.stamp("images/logo.svg") != stamp

        for bad in ("../etc/passwd", ".secret", "images/../.secret", ""):

            with pytest.raises(Fault) as refused: statics.url(bad)

            assert refused.value.code == Code.BAD_REQUEST

        with pytest.raises(Fault) as absent: await statics.read("missing.css")

        assert absent.value.code == Code.NOT_FOUND

    async def test_fs_writes_atomically_and_net_builds_urls ( self, tmp_path: Path ) -> None:

        target = tmp_path / "deep" / "data.json"
        notes  = tmp_path / "notes.txt"

        await fs.write_json(target, { "a": [1, 2] })
        await fs.write_text(notes, "one\n")
        await fs.append(notes, "two\n")

        assert await fs.read_json(target) == { "a": [1, 2] } and await fs.read_text(notes) == "one\ntwo\n"
        assert await fs.exists(target) and await fs.is_dir(target.parent) and await fs.size(notes) == 8
        assert [path.name for path in await fs.list(tmp_path, "*.txt")] == ["notes.txt"]
        assert [path.name for path in await fs.list(tmp_path)] == ["deep", "notes.txt"]
        copied = await fs.copy(notes, tmp_path / "copy.txt")
        moved  = await fs.move(copied, tmp_path / "moved.txt")

        assert await fs.read_text(moved) == "one\ntwo\n" and not await fs.exists(copied)
        assert await fs.remove(notes) and not await fs.remove(notes)
        assert fs.within(tmp_path, target) and not fs.within(tmp_path, tmp_path / ".." / "escape")
        assert (fs.name(target), fs.stem(target), fs.extension(target)) == ("data.json", "data", "json")

        url = net.url("https://api.x.test/", "v1", "/users/", q="a b", page=2)

        assert url == "https://api.x.test/v1/users?q=a+b&page=2"
        assert net.query(url) == { "q": "a b", "page": "2" } and net.host(url) == "api.x.test"
        assert net.origin(url) == "https://api.x.test" and net.origin("nope") == ""
        assert net.is_url(url) and not net.is_url("ftp://x") and net.is_ip("10.0.0.1") and not net.is_ip("10.0.0")
