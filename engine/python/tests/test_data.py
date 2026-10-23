from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from engine.array import Collection, array
from engine.error import Code
from engine.json import json
from engine.number import Money, number
from engine.parse import parse
from engine.rand import rand
from engine.string import Strand, string
from engine.test import expect, test

class Shade(Enum):

    DARK  = "dark"
    LIGHT = "light"

ROWS: list[dict[str, Any]] = [
    { "id": 1, "n": 3, "t": "a" }, { "id": 2, "n": 5, "t": "b" }, { "id": 3, "n": 5, "t": "a" },
]

class TestJson:

    def test_encoding_is_rich_canonical_and_bounded ( self ) -> None:

        document = {
            "d": Decimal("1.50"), "k": Shade.DARK, "s": { 2, 1 }, "b": b"hi", "n": { "m": [10, { "x": 1 }] },
            "w": timedelta(minutes=1),
        }

        expect(json.dumps(document, sort=True)).equals(
            '{"b":"hi","d":"1.50","k":"dark","n":{"m":[10,{"x":1}]},"s":[1,2],"w":60.0}',
        )
        expect(json.pretty({ "a": 1 })).equals('{\n  "a": 1\n}')
        expect((json.parse("{bad", "fallback"), json.parse(b"[1]"), json.parse(5), json.parse("[1]", limit=2))).equals(
            ("fallback", [1], None, None),
        )
        expect((json.valid('{"a":1}'), json.valid("{a}"), json.looks(" [1]"), json.looks("12"))).equals(
            (True, False, True, False),
        )
        expect(json.clone(document)["d"]).equals("1.50")
        expect(json.dumps(object(), lenient=True)).starts_with('"<object')
        expect(json.canonical({ "b": 1, "a": 2 })).equals(b'{"a":2,"b":1}')

        with test.raises(TypeError): json.dumps(object())
        with test.fails(Code.BAD_REQUEST, "json"): json.loads("{nope")
        with test.fails(Code.BAD_REQUEST, "json.size"): json.loads("[1, 2, 3]", limit=4)

    def test_walks_dig_with_wildcards_and_merge_patches_follow_rfc_7396 ( self ) -> None:

        document = { "users": [{ "email": "a@x", "tags": ["x"] }, { "email": "b@x" }], "n": { "m": [10, { "x": 1 }] } }

        expect((json.dig(document, "n.m.1.x"), json.dig(document, "n.m.-1.x"), json.dig(document, "n.q", 0))).equals(
            (1, 1, 0),
        )
        expect(json.dig(document, "users.*.email")).equals(["a@x", "b@x"])
        expect(json.dig(document, "users.*.tags.*")).equals(["x"])
        expect(json.flatten({ "a": { "b": { "c": 1 } }, "d": 2 })).equals({ "a.b.c": 1, "d": 2 })
        expect(json.unflatten({ "a.b": 1 })).equals({ "a": { "b": 1 } })

        stored = { "name": "Ann", "city": "Cairo", "settings": { "theme": "dark", "lang": "ar" } }
        patch  = { "city": None, "settings": { "lang": "en" }, "phone": "+20" }
        merged = json.merge_patch(stored, patch)

        expect(merged).equals({ "name": "Ann", "settings": { "theme": "dark", "lang": "en" }, "phone": "+20" })
        expect(json.merge_patch_of(stored, merged)).equals(patch)
        expect(json.merge_patch(stored, [1])).equals([1])
        expect(json.apply({ "a": 1 }, [{ "op": "add", "path": "/b", "value": 2 }])).equals({ "a": 1, "b": 2 })
        expect(json.redact({ "password": "x", "user": { "api_key": "k", "name": "n" } })).equals(
            { "password": "***", "user": { "api_key": "***", "name": "n" } },
        )

class TestParse:

    def test_casts_are_lenient_on_input_and_strict_on_output ( self ) -> None:

        expect((parse.bool("Yes"), parse.bool("off"), parse.bool(None), parse.bool(2))).equals(
            (True, False, False, True),
        )
        expect((parse.integer("42"), parse.integer("x", 7), parse.integer("3.9"), parse.integer(True))).equals(
            (42, 7, 3, 1),
        )
        expect((parse.float("2.50"), parse.float("nope", 1.5), parse.float("2.346", digits=2))).equals((2.5, 1.5, 2.35))
        expect((parse.decimal("19.999"), parse.positive("-3"))).equals((Decimal("20.00"), 0.0))
        expect((parse.string("  a "), parse.string(None), parse.string(True), parse.text(None))).equals(
            ("a", None, "true", ""),
        )
        expect((parse.list("a, b"), parse.list("[1, 2]"), parse.list(None), parse.list((1,)))).equals(
            (["a", "b"], [1, 2], [], [1]),
        )
        expect((parse.dict('{"k": 1}'), parse.dict("nope"), parse.dict({ 1: 2 }))).equals(({ "k": 1 }, {}, { "1": 2 }))
        expect((parse.empty("  "), parse.empty([]), parse.empty(False), parse.empty(0))).equals(
            (True, True, True, False),
        )
        expect((parse.incoming({ "a": { "b": "[1]" } }, "a.b"), parse.incoming({}, "a.b", "d"))).equals(([1], "d"))
        expect((parse.enum("Dark", Shade), parse.enum("dim", Shade), parse.enum(Shade.LIGHT, Shade))).equals(
            (Shade.DARK, None, Shade.LIGHT),
        )
        expect((str(parse.uuid("0199e5b4-8a4c-7c1e-9d2f-1234567890ab")), parse.uuid("nope"))).equals(
            ("0199e5b4-8a4c-7c1e-9d2f-1234567890ab", None),
        )
        expect((parse.choice("B", ["a", "b"]), parse.choice(2, [1, 2]), parse.choice("z", ["a"], "a"))).equals(
            ("b", 2, "a"),
        )
        expect((parse.amount("1,234.567"), parse.amount("1.234,5"), parse.amount("$ 12"), parse.amount(3))).equals(
            (Decimal("1234.57"), Decimal("1234.50"), Decimal("12.00"), Decimal("3.00")),
        )

    def test_web_shapes_read_headers_queries_and_cookies ( self ) -> None:

        expect(parse.content_type('Multipart/Form-Data; boundary="a;b"; charset=UTF-8')).equals(
            ("multipart/form-data", { "boundary": "a;b", "charset": "UTF-8" }),
        )
        expect((parse.media(None), parse.charset("text/html; charset=ISO-8859-1"), parse.charset(""))).equals(
            ("", "iso-8859-1", "utf-8"),
        )
        expect(parse.accept("text/html;q=0.5, application/json, */*;q=0.1, image/png;q=0")).equals(
            [("application/json", 1.0), ("text/html", 0.5), ("*/*", 0.1)],
        )
        expect((
            parse.prefers("text/*;q=0.9, application/json;q=0.2", ["application/json", "text/csv"]),
            parse.prefers("image/png", ["application/json"]),
        )).equals(("text/csv", None))
        expect(parse.query("?tag[]=a&tag[]=b&q=x&q=y&empty=")).equals(
            { "tag": ["a", "b"], "q": ["x", "y"], "empty": "" },
        )
        expect(parse.cookies('session=abc%20d; theme="dark"; bad key=1')).equals(
            { "session": "abc d", "theme": "dark" },
        )
        expect((parse.bearer("Bearer  tok "), parse.bearer("Basic x"), parse.basic("Basic dXNlcjpwYXNz"))).equals(
            ("tok", None, ("user", "pass")),
        )
        expect((parse.basic("Basic !!"), parse.forwarded("1.1.1.1, 2.2.2.2 ,"))).equals((None, ["1.1.1.1", "2.2.2.2"]))

        with test.fails(Code.BAD_REQUEST, "parse.ranges"): parse.ranges("a-b")
        with test.fails(Code.BAD_REQUEST, "parse.rate"): parse.rate("often")

class TestString:

    def test_cases_inflections_and_codecs ( self ) -> None:

        expect((string.slug("Hello, World!"), string.snake("HelloWorld"), string.kebab("helloWorld"))).equals(
            ("hello-world", "hello_world", "hello-world"),
        )
        expect((string.plural("city"), string.plural("box"), string.plural("cat", 1), string.singular("roles"))).equals(
            ("cities", "boxes", "cat", "role"),
        )
        expect(string.from_base64(string.to_base64("héllo"))).equals("héllo".encode())
        expect(string.from_base64(string.to_base64(b"\xff\x00", url=True).rstrip("="), url=True)).equals(b"\xff\x00")
        expect((string.levenshtein("kitten", "sitting"), string.closest("appel", ["apple", "pear"]))).equals(
            (3, "apple"),
        )
        expect((string.initials("Abdulrahman Yasser"), string.acronym("as soon as possible"))).equals(("AY", "ASAP"))
        expect((string.is_anagram("Listen", "Silent"), string.is_palindrome("A man, a plan, a canal: Panama"))).equals(
            (True, True),
        )

        with test.fails(Code.BAD_REQUEST, "string.base64"): string.from_base64("!!")
        with test.fails(Code.BAD_REQUEST, "string.hex"): string.from_hex("zz")

    def test_arabic_and_unicode_are_first_class ( self ) -> None:

        expect((string.slug("مرحبا بالعالم"), string.slug("Café Ünïcode"), string.slug("مرحبا", unicode=True))).equals(
            ("مرحبا-بالعالم", "cafe-unicode", "مرحبا"),
        )
        expect((string.arabic("أَهْلاً وسَهْلاً"), string.arabic("مدرسة على", fold=True))).equals(
            ("اهلا وسهلا", "مدرسه علي"),
        )
        expect((string.latin_digits("٠١٢٣٤٥٦٧٨٩ \u06f7"), string.arabic_digits("2026"))).equals(
            ("0123456789 7", "٢٠٢٦"),
        )
        expect((string.direction("مرحبا hello"), string.direction("hi مرحبا"), string.direction("123"))).equals(
            ("rtl", "ltr", "neutral"),
        )
        expect((string.is_rtl("abc"), string.has_arabic("abc ب"), string.strip_marks("Crème"))).equals(
            (False, True, "Creme"),
        )
        expect((string.deduplicate("a   b"), string.ucsplit("HelloWorldX"), string.visible_length("é"))).equals(
            ("a b", ["Hello", "World", "X"], 1),
        )
        expect((string.control_free("a\x00b\nc"), string.bidi_safe("a\u202eb"), string.scripts("aب"))).equals(
            ("ab\nc", "ab", ["arabic", "latin"]),
        )

    def test_strands_chain_and_stay_strings ( self ) -> None:

        chained = string.of("  Hello World  ").trim().slug().upper().append("!").prepend(">")

        expect(chained).equals(">HELLO-WORLD!").instance_of(Strand, str)
        expect(string.of("tenant users").studly().limit(9).value()).equals("TenantUs…")
        expect(string.of("a-b-c").replace("-", "+", 1).explode("+")).equals(["a", "b-c"])
        expect(string.of("x").when(True, lambda text: text * 2).unless(False, lambda text: text + "y")).equals("xxy")
        expect(string.of("{name} joined").fill(name="Ann").words()).equals(["Ann", "joined"])
        expect((string.of(None), string.of(b"hi"), string.of("  ").is_empty())).equals(("", "hi", True))

        seen: list[str] = []

        expect(string.of("tap").tap(seen.append).reverse()).equals("pat")
        expect(seen).equals(["tap"])

class TestNumbers:

    def test_math_words_and_formats ( self ) -> None:

        expect((number.clamp(5, 0, 3), number.percent(1, 3), number.pages(45, 20), number.human(1500))).equals(
            (3, 33.33, 3, "1.5K"),
        )
        expect((number.spell(21), number.spell_ordinal(22), number.from_roman("MCMXCIV"), number.roman(1994))).equals(
            ("twenty-one", "twenty-second", 1994, "MCMXCIV"),
        )
        expect((number.is_prime(97), number.factorial(5), number.to_base(-10, 2), number.from_base("ff", 16))).equals(
            (True, 120, "-1010", 255),
        )

        with test.fails(Code.BAD_REQUEST, "number.roman"): number.from_roman("ABC")
        with test.fails(Code.BAD_REQUEST, "number.base"): number.to_base(5, 99)

    def test_money_keeps_currency_exponents_and_never_loses_minor_units ( self ) -> None:

        price = number.money("10.005", "usd")

        expect((str(price), price.minor(), price.currency)).equals(("10.01 USD", 1001, "USD"))
        expect([item.minor() for item in number.money(100, "USD").allocate(1, 1, 1)]).equals([3334, 3333, 3333])
        expect([str(item) for item in number.money(10, "EGP").split(3)]).equals(["3.34 EGP", "3.33 EGP", "3.33 EGP"])
        expect((number.minor(1500, "JPY").format(), number.money("1.2345", "KWD").dump())).equals(
            ("1,500 JPY", { "amount": "1.235", "currency": "KWD", "minor": 1235 }),
        )
        expect((price + price).format()).equals("20.02 USD")
        expect((price - price).is_zero()).true()
        expect((price.times(3).minor(), price.percent(50).format(), price.negate().format())).equals(
            (3003, "5.01 USD", "-10.01 USD"),
        )
        expect((price < price.times(2), Money.total([price, price], "USD").minor())).equals((True, 2002))

        with test.fails(Code.BAD_REQUEST, "money.currency_mismatch"): price.add(number.money(1, "EUR"))
        with test.fails(Code.BAD_REQUEST, "money.currency"): number.money(1, "dollars")
        with test.fails(Code.BAD_REQUEST, "money.amount"): number.money("ten", "USD")
        with test.fails(Code.BAD_REQUEST, "money.ratios"): price.allocate()

class TestArrays:

    def test_verbs_query_and_page_rows ( self ) -> None:

        expect(array.page(45, 2, 20)).equals({ "page": 2, "limit": 20, "total": 45, "pages": 3 })
        expect((array.chunk([1, 2, 3], 2), array.unique([1, 1, 2]), array.group(["aa", "b", "cc"], len))).equals(
            ([[1, 2], [3]], [1, 2], { 2: ["aa", "cc"], 1: ["b"] }),
        )
        expect((array.where(ROWS, "n", 5), array.where(ROWS, "n", ">", 3), array.where_in(ROWS, "id", [1, 3]))).equals(
            (ROWS[1:], ROWS[1:], [ROWS[0], ROWS[2]]),
        )
        expect((array.first_where(ROWS, "t", "b"), array.sole(ROWS, lambda row: row["id"] == 2))).equals(
            (ROWS[1], ROWS[1]),
        )
        expect((array.implode(["a", "b", "c"], ", ", " and "), array.tally("abca"))).equals(
            ("a, b and c", { "a": 2, "b": 1, "c": 1 }),
        )
        expect(array.from_base64(array.to_base64([255, 0, 7], url=True), url=True)).equals([255, 0, 7])

        with test.fails(Code.CONFLICT, "array.sole"): array.sole(ROWS)
        with test.fails(Code.NOT_FOUND, "array.sole"): array.sole([])
        with test.fails(Code.BAD_REQUEST, "array.operator"): array.where(ROWS, "n", "~", 1)
        with test.fails(Code.BAD_REQUEST, "array.size"): array.chunk([1], 0)

    def test_collections_chain_like_laravel ( self ) -> None:

        rows   = array.of(ROWS)
        totals = rows.where("t", "a").pluck("n")

        expect(totals.all()).equals([3, 5])
        expect((totals.sum(), rows.sum(lambda row: row["n"]), rows.avg(lambda row: row["n"]))).equals(
            (8.0, 13.0, 13 / 3),
        )
        expect(rows.sort_by_desc(lambda row: row["n"]).first()).equals(ROWS[1])
        expect(rows.key_by("id")[3]).is_(ROWS[2])
        expect(rows.group_by(lambda row: row["t"])).equals({ "a": [ROWS[0], ROWS[2]], "b": [ROWS[1]] })
        expect(rows.map(lambda row: row["id"]).filter(lambda key: key > 1).push(9).all()).equals([2, 3, 9])
        expect(rows.reject(lambda row: row["n"] > 3).count()).equals(1)
        expect(rows.unique(lambda row: row["t"]).count()).equals(2)
        expect(rows.when(True, lambda found: found.take(1)).unless(True, lambda found: found.skip(1)).all()).equals(
            ROWS[:1],
        )
        expect(rows.page(2, 2)).equals(([ROWS[2]], { "page": 2, "limit": 2, "total": 3, "pages": 2 }))
        expect((rows.contains(ROWS[0]), rows.every(lambda row: row["id"] > 0), rows.is_empty())).equals(
            (True, True, False),
        )
        expect(array.of([3, 1]).merge([2]).reverse().implode()).equals("2, 1, 3")
        expect(Collection([1, 2, 3]).partition(lambda item: item > 1)[0].all()).equals([2, 3])
        expect((rows.min(lambda row: row["n"]), rows.max(lambda row: row["id"]), len(rows), rows[0])).equals(
            (ROWS[0], ROWS[2], 3, ROWS[0]),
        )

        with test.fails(Code.CONFLICT, "array.sole"): rows.sole()

class TestRand:

    def test_randomness_is_strong_bounded_and_uuid7_by_default ( self ) -> None:

        first, second = rand.uuid(), rand.uuid()

        expect((first.version, second.version, rand.uuid(4).version, str(first) < str(second))).equals((7, 7, 4, True))
        expect((rand.otp().isdigit(), len(rand.otp(4)), len(rand.string(24)), len(rand.hex(8)))).equals(
            (True, 4, 24, 16),
        )
        expect([rand.number(3, 5) for _ in range(64)]).each(lambda value: 3 <= value <= 5)
        expect((rand.choice([7]), sorted(rand.shuffle([3, 1, 2])), rand.email("x.test"))).satisfies(
            lambda found: found[0] == 7 and found[1] == [1, 2, 3] and found[2].endswith("@x.test"),
        )

        with test.fails(Code.BAD_REQUEST, "rand.uuid"): rand.uuid(1)
        with test.fails(Code.BAD_REQUEST, "rand.range"): rand.number(5, 3)
        with test.fails(Code.BAD_REQUEST, "rand.empty"): rand.choice([])
