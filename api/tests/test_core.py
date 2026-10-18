from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from email.message import EmailMessage
from pathlib import Path
from typing import Any, ClassVar

from core.array import array
from core.assets import Assets
from core.cache import Cache
from core.config import Config, Env, Settings
from core.crypto import Crypto
from core.date import Moment, Parser, date
from core.error import Code, Fault, Faults
from core.exception import Handler
from core.fs import fs
from core.func import func
from core.http import Envelope
from core.log import log
from core.json import json
from core.mail import Attachment, Mail, MemoryTransport, Message
from core.net import Breaker, Client, net
from core.number import number
from core.rand import rand
from core.string import string
from core.token import Claims, JwtAdapter, Token
from core.validate import Email, Password, validate
from core.parse import parse
from core.thread import thread
from fastapi import FastAPI
from httpx import ASGITransport
from starlette.responses import JSONResponse
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

        assert (parse.bool("Yes"), parse.bool("off"), parse.bool(None), parse.bool(2)) == (True, False, False, True)
        assert (parse.integer("42"), parse.integer("x", 7), parse.integer("3.9"), parse.integer(True)) == (42, 7, 3, 1)
        assert (parse.float("2.50"), parse.float("nope", 1.5), parse.float("2.346", digits=2)) == (2.5, 1.5, 2.35)
        assert parse.decimal("19.999") == Decimal("20.00") and parse.positive("-3") == 0.0
        assert (parse.string("  a "), parse.string(None), parse.string(True)) == ("a", None, "true")
        assert parse.text(None) == ""
        assert (parse.list("a, b"), parse.list("[1, 2]")) == (["a", "b"], [1, 2])
        assert (parse.list(None), parse.list((1,))) == ([], [1])
        assert (parse.dict('{"k": 1}'), parse.dict("nope"), parse.dict({ 1: 2 })) == ({ "k": 1 }, {}, { "1": 2 })
        assert (parse.parse('"q"'), parse.parse("12"), parse.parse("{bad")) == ("q", "12", "{bad")
        assert parse.empty("  ") and parse.empty([]) and parse.empty(False) and not parse.empty(0)
        assert parse.incoming({ "a": { "b": "[1]" } }, "a.b") == [1] and parse.incoming({}, "a.b", "d") == "d"

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

    def test_data_layers_reach_carbon_and_collection_depth ( self ) -> None:

        monday = Moment.of(2026, 10, 19, 9, 30)
        rows: list[dict[str, Any]] = [
            { "id": 1, "n": 3, "t": "a" }, { "id": 2, "n": 5, "t": "b" }, { "id": 3, "n": 5, "t": "a" },
        ]

        def add ( left: int, middle: int, right: int ) -> int:
            return left + middle + right

        assert monday.day_name() == "Monday" and monday.month_name(short=True) == "Oct" and monday.is_business_day()
        assert monday.add_business_days(5).to_date_string() == "2026-10-26"
        assert monday.add_business_days(-1).day_name() == "Friday"
        assert monday.business_days_until(monday.add(days=7)) == 5
        assert monday.next("friday").at.day == 23 and monday.previous("monday").at.day == 12
        assert monday.next("monday").at.day == 26 and monday.nth_of_month(3, "wed") is not None
        assert monday.first_of_month("thursday").at.day == 1 and monday.last_of_month("saturday").at.day == 31
        assert monday.nth_of_month(5, "sunday") is None and monday.week_of_month() == 4
        assert not monday.is_last_of_month() and Moment.of(2026, 10, 31).is_last_of_month()
        assert Moment.of(2026, 10, 1).is_first_of_month() and not monday.is_dst()
        assert monday.set(hour=12).at.hour == 12 and monday.floor("hour").at.minute == 0
        assert monday.round("hour").at.hour == 10 and monday.ceil("hour").at.hour == 10
        assert monday.floor("hour").stamp_ms() % 3_600_000 == 0 and monday.to_time_string() == "09:30:00"
        assert monday.to_datetime_string() == "2026-10-19 09:30:00" and monday.calendar_week() == (2026, 43)
        assert Moment.of(2000, 2, 29).age(Moment.of(2026, 2, 28)) == 25
        assert Moment.of(2000, 2, 29).age(Moment.of(2026, 3, 1)) == 26
        assert date.age(datetime(2000, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)) == 26
        assert date.is_leap(2024) and not date.is_leap(2100) and date.days_in(2026, 2) == 28
        assert "Africa/Cairo" in date.zones() and date.business_days(monday.at, monday.add(days=7).at) == 5

        assert string.levenshtein("kitten", "sitting") == 3 and string.similarity("abc", "abc") == 1.0
        assert string.closest("appel", ["apple", "pear"]) == "apple" and string.closest("zzz", ["apple"]) is None
        assert string.common_prefix("interstellar", "internet") == "inter"
        assert string.common_suffix("walking", "talking") == "alking"
        assert string.initials("Abdulrahman Yasser") == "AY" and string.acronym("as soon as possible") == "ASAP"
        assert string.digits("+20 109") == "20109" and string.letters("a1b2") == "ab"
        assert string.char_at("abc", -1) == "c" and string.char_at("abc", 9) == ""
        assert string.position("hello", "l") == 2 and string.position("hello", "z") is None
        assert string.take("hello", 2) == "he" and string.take("hello", -2) == "lo"
        assert string.substr("hello", 1, 3) == "ell"
        assert string.surround("x", "*") == "*x*" and string.unwrap("[x]", "[", "]") == "x"
        assert string.is_anagram("Listen", "Silent") and string.is_palindrome("A man, a plan, a canal: Panama")
        assert string.diff("a\nb", "a\nc")[1:] == ["-b", "+c"]

        assert array.where(rows, "n", 5) == rows[1:] and array.where(rows, "n", ">", 3) == rows[1:]
        assert array.where_in(rows, "id", [1, 3]) == [rows[0], rows[2]]
        assert array.where_not_in(rows, "id", [1]) == rows[1:]
        assert array.first_where(rows, "t", "b") == rows[1] and array.sole(rows, lambda row: row["id"] == 2) == rows[1]
        assert array.key_by(rows, "id")[3] == rows[2] and array.min_by(rows, lambda row: row["n"]) == rows[0]
        assert array.max_by(rows, lambda row: row["id"]) == rows[2]
        assert array.avg_by(rows, lambda row: row["n"]) == 13 / 3
        assert array.duplicates([1, 2, 1, 3, 2]) == [1, 2] and array.take_while([1, 2, 5, 1], lambda n: n < 3) == [1, 2]
        assert array.skip_while([1, 2, 5, 1], lambda n: n < 3) == [5, 1]
        assert array.split([1, 2, 3, 4, 5], 2) == [[1, 2, 3], [4, 5]]
        assert array.transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]] and array.nth([0, 1, 2, 3, 4], 2) == [0, 2, 4]
        assert array.flat_map([1, 2], lambda n: [n, n]) == [1, 1, 2, 2]
        assert array.combine(["a", "b"], [1, 2]) == { "a": 1, "b": 2 }
        assert array.divide([1, 2, 3], lambda n: n % 2 == 1) == ([1, 3], [2]) and array.pad([1], 3, 0) == [1, 0, 0]
        assert array.pad([1], -3, 0) == [0, 0, 1] and array.prepend([2], 0, 1) == [0, 1, 2]
        assert array.collapse([[1], [2, 3]]) == [1, 2, 3] and array.tally("abca") == { "a": 2, "b": 1, "c": 1 }
        assert array.mode([1, 2, 2]) == 2 and array.implode(["a", "b", "c"], ", ", " and ") == "a, b and c"
        assert array.pluck_many(rows, "id")[0] == { "id": 1 } and array.where_not_none(rows, "t") == rows

        with pytest.raises(ValueError): array.sole(rows)
        with pytest.raises(ValueError): array.where(rows, "n", "~", 1)

        assert number.spell(0) == "zero" and number.spell(21) == "twenty-one" and number.spell(-5) == "minus five"
        assert number.spell(1_234_567) == "one million two hundred thirty-four thousand five hundred sixty-seven"
        assert number.spell_ordinal(1) == "first" and number.spell_ordinal(22) == "twenty-second"
        assert number.spell_ordinal(30) == "thirtieth" and number.spell_ordinal(100) == "one hundredth"
        assert number.from_roman("MCMXCIV") == 1994 and number.roman(1994) == "MCMXCIV"
        assert number.is_prime(97) and not number.is_prime(91) and number.factorial(5) == 120
        assert number.digit_sum(-1234) == 10 and number.digits(907) == [9, 0, 7]
        assert number.is_power_of(64, 2) and not number.is_power_of(48, 2) and number.next_power_of(70) == 128
        assert number.lerp(0, 10, 0.25) == 2.5 and number.normalize(5, 0, 10) == 0.5
        assert number.map_range(5, 0, 10, 0, 100) == 50 and number.to_base(255, 16) == "ff"
        assert number.to_base(-10, 2) == "-1010" and number.from_base("ff", 16) == 255

        with pytest.raises(ValueError): number.from_roman("ABC")

        assert -10 < rand.gaussian(0, 1) < 10 and rand.boolean(1.0) and not rand.boolean(0.0)
        assert rand.sign() in (1, -1) and len(rand.digits(6)) == 6 and rand.ipv4().startswith("10.")
        assert not rand.ipv4(private=False).startswith("0.") and rand.ipv6().count(":") == 7
        assert rand.mac().count(":") == 5
        assert len(rand.words(4)) == 4 and rand.sentence(3).endswith(".") and rand.paragraph(2, 2).count(".") == 2
        assert rand.title(2)[0].isupper() and rand.email("x.test").endswith("@x.test")
        assert rand.url(domain="x.test").startswith("https://x.test/") and rand.phone().startswith("+1555")
        assert -90 <= rand.latitude() <= 90 and -180 <= rand.longitude() <= 180 and 1 <= rand.amount(1, 2) <= 2
        assert rand.domain("test").endswith(".test") and rand.engine() is rand.engine()

        assert func.curry(add)(1)(2)(3) == 6 and func.curry(add)(1, 2)(3) == 6 and func.curry(add, 3)(1)(2, 3) == 6
        assert func.juxt(len, str.upper)("ab") == [2, "AB"] and func.unary(int)("7") == 7

        later = func.after(2, lambda: "go")
        early = func.before(3, lambda n: n * 2)

        assert later() is None and later() == "go" and [early(1), early(2), early(3)] == [2, 4, 4]

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

        assert validate.make(data, rules) == { "age": ["Must be at least 18"], "start": ["Must be before end"] }
        assert validate.rules.passes({ "a": "x" }, { "a": "required|alpha" })
        assert validate.rules.fails({}, { "a": "required" })
        assert validate.make({ "n": 5 }, { "n": "bail|string|min:9" }) == { "n": ["Must be a string"] }
        assert validate.make(filled, { "flag": "accepted", "code": "digits:4", "other": "filled" }) == {
            "other": ["This field must not be empty"],
        }
        assert validate.make({ "a": 1, "b": 2 }, { "b": "gt:a|different:a", "a": "lt:b|same:b" }) == {
            "a": ["Must match b"],
        }
        assert validate.make({ "n": "7" }, { "n": "numeric|between:1,5" }) == { "n": ["Must be between 1 and 5"] }
        assert validate.make({}, { "n": "required" }, { "n.required": "Give n" }) == { "n": ["Give n"] }
        assert validate.make({ "n": "x" }, { "n": "integer" }, { "integer": "Whole" }) == { "n": ["Whole"] }
        assert validate.validated({ "x": "ok", "y": "ignored" }, { "x": "required" }) == { "x": "ok" }

        with pytest.raises(Fault) as refused: validate.validated({}, { "x": "required" })
        with pytest.raises(ValueError): validate.make({ "x": 1 }, { "x": "nope" })

        assert refused.value.code == Code.VALIDATION and refused.value.errors == { "x": ["This field is required"] }

        validate.rule("even", lambda c: None if int(c.value) % 2 == 0 else "Must be even")

        assert validate.make({ "n": 3 }, { "n": "even" }) == { "n": ["Must be even"] }
        assert "even" in validate.rules.names()

        patched = json.apply(doc, ops)

        assert patched == { "a": { "b": [3] }, "k": "w", "first": 1, "again": "w" } and doc["a"]["b"] == [1, 2]
        assert json.pointer(patched, "/a/b/0") == 3 and json.pointer(patched, "/nope", 9) == 9
        assert json.has_pointer(patched, "/k") and json.pointer_of("a", "x/y", 0) == "/a/x~1y/0"
        assert json.changes({ "a": 1, "b": 2 }, { "a": 1, "b": 3, "c": 4 }) == [
            { "op": "replace", "path": "/b", "value": 3 }, { "op": "add", "path": "/c", "value": 4 },
        ]
        assert json.apply({ "a": 1, "b": 2 }, json.changes({ "a": 1, "b": 2 }, { "b": 3 })) == { "b": 3 }
        assert json.same({ "a": 1, "b": 2 }, { "b": 2, "a": 1 }) and len(json.checksum({})) == 32
        assert json.size({ "a": 1 }) == 7
        assert json.redact(hidden) == {
            "password": "***", "nested": { "api_key": "***", "ok": 1 }, "list": [{ "token": "***" }],
        }

        with pytest.raises(Fault): json.apply({}, [{ "op": "test", "path": "/x", "value": 1 }])
        with pytest.raises(Fault): json.apply({}, [{ "op": "replace", "path": "/x", "value": 1 }])
        with pytest.raises(Fault): json.apply({}, [{ "op": "jump", "path": "/x" }])

        assert parse.key_values("a=1, b = two,junk") == { "a": "1", "b": "two" }
        assert parse.csv_line('x, "y, z", 3') == ["x", "y, z", "3"]
        assert parse.csv_rows("a,b\n1,2\n") == [["a", "b"], ["1", "2"]]
        assert parse.tags("Go, go ,rust,,") == ["go", "rust"]
        assert parse.ranges("1-3,7,10-8") == [1, 2, 3, 7, 10, 9, 8]
        assert parse.semver("v1.2.3-rc.1+build5") == {
            "major": 1, "minor": 2, "patch": 3, "pre": "rc.1", "build": "build5",
        }
        assert parse.semver("1.2") is None and parse.version("v2.10.1-beta") == (2, 10, 1)
        assert parse.compare_versions("1.10", "1.9") == 1 and parse.compare_versions("1.2.0", "1.2") == 0
        assert parse.satisfies("1.5", "1.0", "2.0") and not parse.satisfies("2.1", "1.0", "2.0")
        assert parse.numbers("x -1.5 and 2") == [-1.5, 2.0]
        assert parse.words("hello, world_x!") == ["hello", "world", "x"]
        assert parse.mentions("hi @ann and @bob.k, mail x@y") == ["ann", "bob.k"]
        assert parse.hashtags("#go #rust") == ["go", "rust"]
        assert parse.lines("a\n\n b \n") == ["a", " b"]
        assert parse.flags(["--dry", "--name=x", "pos"]) == { "dry": True, "name": "x" }

        with pytest.raises(ValueError): parse.ranges("a-b")

        port = net.free_port()

        assert port > 0 and not await net.port_open("127.0.0.1", port, 0.5)
        assert await net.wait_port("127.0.0.1", port, within=0.2, every=0.05) is False

        def hang_up ( _reader: asyncio.StreamReader, writer: asyncio.StreamWriter ) -> None:
            writer.close()

        server = await asyncio.start_server(hang_up, "127.0.0.1", port)

        try: assert await net.port_open("127.0.0.1", port) and await net.wait_port("127.0.0.1", port, within=1)
        finally:

            server.close()

            await server.wait_closed()

        assert "127.0.0.1" in await net.resolve("localhost") and await net.resolve("nope.invalid") == []
        assert net.describe_host()["hostname"] and net.local_ip()

        with pytest.raises(Fault): await net.require_port("127.0.0.1", port, within=0.2)

    @pytest.mark.anyio
    async def test_files_archives_editors_phrases_regex_breakers_and_pages ( self, tmp_path: Path ) -> None:

        root   = tmp_path / "scan"
        cfg    = tmp_path / "app.env"
        text   = tmp_path / "t.txt"
        now    = Moment.of(2026, 10, 19, 9, 30)
        spoken = Parser()
        api    = FastAPI()

        def when ( phrase: str ) -> Moment:

            found = spoken.parse(phrase, now, UTC)

            assert isinstance(found, Moment)

            return found

        def before ( method: str, _url: str ) -> None:
            seen.append(("before", method))

        def failed ( _method: str, _url: str, fault: Fault ) -> None:
            seen.append(("error", fault.reason))
        seen: list[tuple[str, object]] = []
        times  = [0.0]

        @api.get("/items")
        async def items ( page: int = 1 ) -> JSONResponse:
            return JSONResponse({ "data": [page], "next": f"/items?page={page + 1}" if page < 3 else None })

        @api.get("/boom")
        async def boom () -> JSONResponse:
            return JSONResponse({ "e": 1 }, status_code=503)

        (root / "a").mkdir(parents=True)
        (root / "empty").mkdir()

        await fs.write_text(root / "a" / "note.txt", "hello\nworld\n")
        await fs.write_bytes(root / "a" / "pic.png", b"\x89PNG")
        await fs.write_text(root / "zero.log", "")

        assert fs.file.kind("x.png") == "image" and fs.file.kind("x.tar.gz") == "archive"
        assert fs.file.kind("x.py") == "code"
        assert fs.file.kind("x.pdf") == "document" and fs.file.kind("x.mp3") == "audio"
        assert fs.file.kind("x.bin") == "executable"
        assert fs.file.kind("x.xyz") == "other" and fs.file.is_image("a.jpg") and fs.file.is_text("a.json")
        assert fs.file.is_media("a.mp4") and "font" in fs.file.kinds() and fs.file.is_archive("a.zip")

        grouped = await fs.dir.categorize(root)

        assert sorted(grouped) == ["image", "other", "text"] and grouped["text"] == [root / "a" / "note.txt"]
        assert await fs.dir.images(root) == [root / "a" / "pic.png"]
        assert await fs.dir.empty_dirs(root) == [root / "empty"]
        assert await fs.dir.empty_files(root) == [root / "zero.log"] and await fs.dir.depth(root) == 2
        assert await fs.dir.search(root, "note") == [root / "a" / "note.txt"]
        assert await fs.dir.search(root, "world", names_only=False) == [root / "a" / "note.txt"]
        assert (await fs.dir.summary(root))["files"] == 3 and (await fs.dir.disk_usage(root))["total"] > 0
        assert await fs.dir.select(root, lambda path: path.suffix == ".png") == [root / "a" / "pic.png"]

        archive = await fs.archive.zip(tmp_path / "out" / "bundle.zip", root / "a")

        assert await fs.archive.members(archive) == ["a/note.txt", "a/pic.png"]

        extracted = await fs.archive.extract(archive, tmp_path / "unz")

        assert sorted(path.name for path in extracted) == ["note.txt", "pic.png"]
        assert await fs.read_text(tmp_path / "unz" / "a" / "note.txt") == "hello\nworld\n"

        tarred = await fs.archive.compress(tmp_path / "out" / "bundle.tar.gz", root / "a" / "note.txt")

        assert await fs.archive.members(tarred) == ["note.txt"] and fs.archive.is_archive(tarred)
        assert not fs.archive.is_archive("x.txt") and len(await fs.archive.untar(tarred, tmp_path / "unt")) == 1

        with pytest.raises(Fault): await fs.archive.extract(tmp_path / "nope.rar", tmp_path)

        await fs.write_text(cfg, "# head\nA=1\nexport B='two words'\n")

        assert fs.editor.env_to_dict(await fs.read_text(cfg)) == { "A": "1", "B": "two words" }

        await fs.editor.env_set(cfg, "A", 2)
        await fs.editor.env_set(cfg, "C", "x y")

        assert await fs.editor.env_get(cfg, "A") == "2" and await fs.editor.env_get(cfg, "C") == "x y"
        assert await fs.editor.env_get(cfg, "Z", "d") == "d" and await fs.editor.env_delete(cfg, "B") == 1
        assert "B=" not in await fs.read_text(cfg)
        assert fs.editor.dict_to_env({ "K": "v", "S": "a b" }) == "K=v\nS='a b'\n"

        await fs.editor.env_merge(cfg, { "D": 4 })
        await fs.write_text(text, "one\ntwo\nthree\n")

        assert (await fs.editor.env_load(cfg))["D"] == "4" and await fs.editor.insert_after(text, "one", "1.5")
        assert await fs.editor.insert_before(text, "three", "2.5")
        assert not await fs.editor.insert_after(text, "zzz", "x")
        assert await fs.editor.lines(text) == ["one", "1.5", "two", "2.5", "three"]
        assert await fs.editor.delete_lines(text, lambda line: "." in line) == 2

        await fs.editor.replace_line(text, 2, "TWO")
        await fs.editor.insert_line(text, 1, "zero")

        assert await fs.editor.lines(text) == ["zero", "one", "TWO", "three"]
        assert await fs.editor.ensure_line(text, "four")
        assert not await fs.editor.ensure_line(text, "four")

        await fs.write_text(text, "<a>old</a>")

        assert await fs.editor.replace_between(text, "<a>", "</a>", "new") and await fs.read_text(text) == "<a>new</a>"
        assert fs.editor.extract_between("x[1]y", "[", "]") == "1" and fs.editor.extract_between("x", "[", "]") is None

        await fs.editor.map_lines(text, str.upper)

        assert await fs.read_text(text) == "<A>NEW</A>\n"

        with pytest.raises(IndexError): await fs.editor.replace_line(text, 9, "x")

        backup = await fs.file.backup(text)

        assert backup.name == "t.txt.bak" and await fs.exists(backup)
        assert set(await fs.file.times(text)) == { "created", "modified", "accessed" }

        await fs.file.chmod(text, 0o755)

        assert await fs.file.is_runnable(text) and not await fs.file.is_runnable(tmp_path / "nope")

        assert string.search("order 42 shipped", r"\d+") == "42" and string.fullmatch("abc", r"[a-c]+")
        assert not string.fullmatch("abcd", r"[a-c]+") and string.sub("a1b2", r"\d", "#") == "a#b#"
        assert string.groups("2026-10-18", r"(?P<y>\d{4})-(?P<m>\d{2})") == { "y": "2026", "m": "10" }
        assert string.split_regex("a, b;c", r"[,;]\s*") == ["a", "b", "c"] and string.escape("a.b") == "a\\.b"
        assert string.equals_ignore_case("Straße", "STRASSE")
        assert string.replace_insensitive("Hello hello", "hello", "bye") == "bye bye"
        assert string.strip_symbols("a-b, c!") == "ab c" and string.char_count("a b", spaces=False) == 2
        assert string.hash("x", size=8) == "2d711642"
        assert string.title_safe("the lord of the rings") == "The Lord of the Rings"
        assert string.preserve_case("Hello", "world") == "World" and string.preserve_case("HI", "yo") == "YO"

        assert when("next friday").to_date_string() == "2026-10-23"
        assert when("in 3 days").at.day == 22 and when("2 hours ago").at.hour == 7
        assert when("an hour from now").at.hour == 10
        assert when("last monday").at.day == 12
        assert when("this month").at.day == 1 and when("next month").month() == 11
        assert when("last year").year() == 2025 and when("end of day").at.hour == 23
        assert when("start of week").at.day == 19
        assert when("end of tomorrow").at.day == 20
        assert when("tomorrow at 3pm").at.hour == 15
        assert when("friday noon").at.hour == 12
        assert when("friday noon").at.day == 23
        assert when("25 december 2026").month() == 12
        assert when("14/07/2026").at.day == 14 and spoken.parse("gibberish", now, UTC) is None
        assert when("at 10:15").at.minute == 15 and when("at 10:15").at.day == 19
        assert when("monday").at.day == 19 and when("next quarter").month() == 1
        assert Moment.parse("next monday").at.weekday() == 0 and date.is_valid("in 2 weeks")
        assert date.parse("yesterday") < date.now()

        with pytest.raises(Fault): Moment.parse("the day after the flood")

        fuse   = Breaker("api", failures=2, reset=60)
        client = Client("http://api.test", transport=ASGITransport(app=api), breaker=fuse)

        client.on_before(before).on_after(lambda reply: seen.append(("after", reply.status))).on_error(failed)

        assert [item async for item in client.pages("/items")] == [1, 2, 3] and seen[0] == ("before", "GET")
        assert seen[1] == ("after", 200) and (await client.get("/boom")).status == 503
        assert (await client.get("/boom")).status == 503

        with pytest.raises(Fault) as tripped: await client.get("/items")

        held = client.breaker()

        assert tripped.value.reason == "breaker.api" and held is not None and held.state == "open" and held.trips == 1
        assert client.with_bearer("t").with_basic("u", "p").with_header("X-A", "1") is client

        breaker = Breaker("x", failures=1, reset=10, clock=lambda: times[0])

        breaker.fail()

        assert not breaker.allow() and breaker.is_open()

        times[0] = 11.0

        assert breaker.allow() and breaker.state == "half_open"

        breaker.fail()

        assert breaker.state == "open" and breaker.trips == 2

        breaker.succeed()

        assert breaker.state == "closed" and breaker.describe()["trips"] == 2

        breaker.force_open()

        with pytest.raises(Fault): breaker.guard()

        assert await thread.compute(pow, 2, 10) == 1024
        assert array.reduce([1, 2, 3], lambda total, item: total + item, 0) == 6

        thread.shutdown_processes()

        await client.close()

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

        class Leveled(Handler):

            levels : ClassVar[Mapping[type[BaseException], str]] = { TimeoutError: "warning" }

        assert Leveled().level_of(TimeoutError()) == "warning" and Leveled().level_of(ValueError()) is None
        assert Leveled().handle(TimeoutError("slow")).code == Code.INTERNAL

        log.share(tenant="acme")

        assert log.shared()["tenant"] == "acme"

        log.unshare("tenant")

        assert "tenant" not in log.shared()
        assert func.load("core.string:string") is string and func.load("core.rand").rand is rand
        assert any(value is Handler for value in func.discover("core.exception", callable))

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

    @pytest.mark.anyio
    async def test_files_seal_and_open_with_the_rotating_keys ( self, tmp_path: Path ) -> None:

        vault = Crypto()

        vault.setup([vault.key()])

        await fs.write_text(tmp_path / "secret.txt", "top secret")

        sealed = await vault.seal_file(tmp_path / "secret.txt")
        opened = await vault.open_file(sealed, tmp_path / "back.txt")

        assert sealed.name == "secret.txt.sealed" and await fs.read_text(opened) == "top secret"
        assert vault.is_sealed(await fs.read_text(sealed)) and not vault.is_sealed("plain")

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

        origin = fs.drivers.local("origin", tmp_path / "origin", "/o")
        mirror = fs.drivers.local("mirror", tmp_path / "mirror")

        assert await origin.put("a/one.txt", b"1", "text/plain") == 1 and await origin.upload(moved, "b/moved.txt") == 8
        assert await origin.sync(mirror) == 2 and await mirror.list() == ["a/one.txt", "b/moved.txt"]
        assert await origin.sync(mirror) == 0 and origin.url("a/one.txt") == "/o/a/one.txt" and mirror.url("x") is None
        assert await mirror.download("b/moved.txt", tmp_path / "back.txt") == 8
        assert await fs.read_text(tmp_path / "back.txt") == "one\ntwo\n"
        assert await mirror.remove("a/one.txt") and not await mirror.exists("a/one.txt")
        assert not await mirror.remove("a/one.txt") and fs.drivers.has("mirror")
        assert { "mirror", "origin" } <= set(fs.drivers.names()) and fs.driver("origin") is origin
        assert fs.use("origin") is origin
        assert await fs.drivers.sync("origin", "mirror") == 1
        assert fs.drivers.forget("origin") and fs.drivers.forget("mirror")
        assert "origin" not in fs.drivers.describe()["drivers"]

        with pytest.raises(Fault): fs.drivers.use("origin")

        url = net.url("https://api.x.test/", "v1", "/users/", q="a b", page=2)

        assert url == "https://api.x.test/v1/users?q=a+b&page=2"
        assert net.query(url) == { "q": "a b", "page": "2" } and net.host(url) == "api.x.test"
        assert net.origin(url) == "https://api.x.test" and net.origin("nope") == ""
        assert net.is_url(url) and not net.is_url("ftp://x") and net.is_ip("10.0.0.1") and not net.is_ip("10.0.0")
