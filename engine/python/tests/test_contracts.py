from collections.abc import Callable, Coroutine, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from engine.domain import Contact, Domains
from engine.error import Fault
from engine.gateway import Payments, Payout
from engine.json import Schema, json
from engine.llm import Attachment, ChatGpt, Gemini, Message, Model, Options
from engine.net import Answer, Ask, Transport, net
from engine.number import Money
from engine.sms import Text, Twilio, WhatsApp
from engine.test import expect
import jsonschema, os, pytest, re, yaml

type Spec = dict[str, Any]
type Routes = list[tuple[str, object]]

FOLDER  = Path(os.environ.get("CONTRACT_SPECS", "/nonexistent"))
CONTACT = Contact(
    name="Ann Lee", email="a@e.com", phone="+1.5550001", street="1 St", city="X", state="CA", postal_code="90001",
    country="US",
)
MONEY   = { "currency_code": "USD", "value": "10.00" }
ORDER   = {
    "id": "O1", "status": "COMPLETED", "intent": "AUTHORIZE",
    "purchase_units": [{ "reference_id": "r", "amount": MONEY, "payments": {
        "authorizations": [{ "id": "AU1", "status": "CREATED", "amount": MONEY }],
        "captures": [{ "id": "CA1", "status": "COMPLETED", "amount": MONEY }],
    } }],
}
SIGNED  = {
    "paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.paypal.com/v1/notifications/certs/CERT-1",
    "paypal-transmission-id": "69cd13f0-d67a-11e5-baa3-778b53f4ae55",
    "paypal-transmission-time": "2026-10-19T08:00:00Z",
    "paypal-transmission-sig": "lmI95Jx3Y9nhR5SJWlHVIWpg4AgFk7n9bCHSRxbrd8A9zrhdu2rMyFrmz+Zjh3s3bo==",
}

ANSWER  = Schema({
    "type": "object", "additionalProperties": False, "required": ["answer"],
    "properties": { "answer": { "type": "string", "minLength": 1 } },
})

def specs () -> Path:

    if not FOLDER.is_dir(): pytest.skip("set CONTRACT_SPECS to a folder of the official provider specs")

    return FOLDER

def recorder ( seen: list[Ask], routes: Routes ) -> Transport:

    def answer ( asked: Ask ) -> Answer:

        seen.append(asked)

        body = next((reply for pattern, reply in routes if re.search(pattern, urlsplit(asked.url).path)), {})

        if isinstance(body, bytes): return 200, body, { "content-type": "text/event-stream" }

        return 200, json.encode(body), { "content-type": "application/json" }

    return net.mocked(answer)

async def calls ( *works: Coroutine[Any, Any, object] ) -> None:

    for work in works:

        try: await work
        except Fault:
            continue

def resolve ( node: object, spec: Spec, depth: int = 0 ) -> Any:

    if depth > 40: return {}
    if isinstance(node, list): return [resolve(item, spec, depth + 1) for item in node]
    if not isinstance(node, dict): return node
    if "$ref" in node: return resolve(pointer(spec, str(node["$ref"])), spec, depth + 1)

    made = { key: resolve(value, spec, depth + 1) for key, value in node.items() }

    if made.get("nullable") is True and "type" in made: made["type"] = [made["type"], "null"]

    return made

def pointer ( spec: Spec, ref: str ) -> Any:

    found: Any = spec

    for part in ref.lstrip("#/").split("/"): found = found[part]

    return found

def flattened ( schema: Spec ) -> Spec:

    if "allOf" not in schema: return schema

    merged: Spec = { "type": "object", "properties": {}, "required": [] }
    closed = False

    for part in (flattened(item) for item in schema["allOf"]):

        merged["properties"].update(part.get("properties", {}))
        merged["required"].extend(part.get("required", []))
        closed = closed or part.get("additionalProperties") is False

    if closed: merged["additionalProperties"] = False

    return merged

def fields ( schema: Spec ) -> Spec:

    found = dict(schema.get("properties", {}))

    for key in ("allOf", "anyOf", "oneOf"):

        for part in schema.get(key, []): found.update(fields(part))

    return found

def operation ( spec: Spec, method: str, path: str ) -> Spec | None:

    for template, item in spec["paths"].items():

        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template))

        if re.fullmatch(pattern, path) and method.lower() in item: return dict(item[method.lower()])

    return None

def body_of ( asked: Ask, kind: str, schema: Spec ) -> Any:

    if kind == "application/json": return json.loads(asked.body)

    known = fields(schema)

    return {
        key: values if len(values) > 1 or known.get(key, {}).get("type") == "array" else values[0]
        for key, values in parse_qs(asked.body.decode()).items()
    }

def schema_of ( spec: Spec, op: Spec, kind: str, body: bytes ) -> Spec | None:

    found = (((op.get("requestBody") or {}).get("content") or {}).get(kind) or {}).get("schema")

    if found is None: return None

    schema = resolve(found, spec)
    mapped = (schema.get("discriminator") or {}).get("mapping")

    if mapped and kind == "application/json":

        chosen = mapped.get(json.loads(body).get("type", ""))

        if chosen: schema = resolve(pointer(spec, chosen), spec)

    return flattened(schema)

def problems ( spec: Spec, asked: Ask, prefix: str = "" ) -> list[str]:

    path = urlsplit(asked.url).path.removeprefix(prefix)
    op   = operation(spec, asked.method, path)

    if op is None: return [f"{asked.method} {path} is not in the spec"]
    if not asked.body: return []

    kind   = asked.headers.get("content-type", "").split(";")[0]
    schema = schema_of(spec, op, kind, asked.body)

    if schema is None: return [f"{asked.method} {path} sends an undeclared {kind} body"]

    body  = body_of(asked, kind, schema)
    known = fields(schema)
    extra = sorted(set(body) - set(known)) if known and isinstance(body, dict) else []
    found = [f"{asked.method} {path} sends unknown fields {extra}"] if extra else []
    found.extend(
        f"{asked.method} {path} {'/'.join(map(str, error.path)) or '<root>'}: {error.message[:120]}"
        for error in jsonschema.Draft202012Validator(schema).iter_errors(body)
    )

    return found

def checked ( spec: Spec | Callable[[Ask], Spec], seen: list[Ask], prefix: str = "", skip: str = "" ) -> list[str]:

    found: list[str] = []

    for asked in seen:

        if skip and asked.url.endswith(skip): continue

        found.extend(problems(spec(asked) if callable(spec) else spec, asked, prefix))

    return found

def loaded ( name: str ) -> Spec:

    path = specs() / name
    data: Spec = yaml.safe_load(path.read_text()) if name.endswith(".yaml") else json.loads(path.read_text())

    return data

class TestContracts:

    async def test_paypal_orders_payments_payouts_and_webhooks_follow_the_official_specs ( self ) -> None:

        seen: list[Ask] = []

        books = [loaded(f"paypal_{name}.json") for name in (
            "checkout_orders_v2", "payments_payment_v2", "payments_payouts_batch_v1", "notifications_webhooks_v1",
        )]
        own   = Payments()
        wire  = recorder(seen, [
            (r"/v1/oauth2/token", { "access_token": "A", "expires_in": 3600 }), (r"/v2/checkout/orders", ORDER),
            (r"/verify-webhook-signature", { "verification_status": "SUCCESS" }),
        ])

        own.connect("paypal", { "client_id": "c", "secret_key": "s", "sandbox": True, "webhook_id": "W" }, wire)

        await calls(
            own.charge("10.00", "USD", "r").returns("https://e.co").customer("Ann", "a@e.com").authorize().deposit(),
            own.find("O1"), own.capture("O1"), own.void("O1"), own.refund("CA1", Money.of("4.00", "USD"), "late"),
            own.withdraw(Payout(amount=Money.of("5.00", "USD"), reference="w-1", recipient="a@e.com")),
            own.webhook(json.encode({ "id": "E", "event_type": "X", "resource": ORDER }), SIGNED),
        )

        def book ( asked: Ask ) -> Spec:

            path = urlsplit(asked.url).path

            return next((spec for spec in books if operation(spec, asked.method, path)), books[0])

        expect(len(seen)).above(9)
        expect(checked(book, seen, skip="/v1/oauth2/token")).equals([])

    async def test_openai_twilio_vercel_and_cloudflare_requests_follow_their_official_specs ( self ) -> None:

        seen: list[Ask] = []

        chunk  = b'data: {"choices":[{"delta":{"content":"a"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        gpt    = ChatGpt(Model("gpt-5", key="k"), recorder(seen, [(r"/models", { "data": [] })]))
        stream = ChatGpt(Model("gpt-5", key="k"), recorder(seen, [(r"/chat/completions", chunk)]))
        files  = (Attachment("a.png", b"\x89PNG", "image/png"), Attachment("d.pdf", b"%PDF", "application/pdf"))
        tuned  = Options(
            system="s", temperature=0.2, max_tokens=50, top_p=0.9, stop=("END",), json=True, metadata={ "u": "1" },
            seed=7, presence=0.5, frequency=0.2, effort="high",
        )

        async def drain () -> None:

            async for _ in stream.stream([Message.user("go")], Options()): pass

        asked   = [Message.user("hi", *files, Attachment.text("n.txt", "x"))]
        rows    = { "data": [{ "index": 0, "embedding": [0.1, 0.2] }, { "index": 1, "embedding": [0.3, 0.4] }] }
        vectors = ChatGpt(Model("text-embedding-3-small", key="k"), recorder(seen, [(r"/embeddings", rows)]))
        shaped  = Options(schema=ANSWER, max_tokens=20)

        await calls(gpt.complete(asked, tuned), gpt.models(), drain(), gpt.complete(asked, shaped))
        await calls(vectors.embed(["refunds", "shipping"], query=True))

        expect(len(seen)).equals(5)
        expect(checked(loaded("openai.json"), seen, "/v1")).equals([])
        expect(json.loads(seen[3].body)["response_format"]).subset({
            "type": "json_schema", "json_schema.strict": True,
        })

        seen.clear()

        twilio = Twilio("AC1", "tok", "+15550001", transport=recorder(seen, [(r"Messages", { "sid": "SM1" })]))

        media  = Text.compose("hi").to("+201000000000").media("https://e.com/a.png", "https://e.com/b.png")

        await calls(twilio.send(media, ""))

        expect(len(seen)).equals(1)
        expect(checked(loaded("twilio.json"), seen)).equals([])

        seen.clear()

        vercel = Domains()
        offers = { "results": [{ "domain": "a.com", "available": True, "price": 11.25, "renewalPrice": 11.25 }] }

        vercel.connect("vercel", token="t", project="p", team="team_1", transport=recorder(seen, [
            (r"/search", offers), (r"/records$", { "records": [] }),
            (r"/domains/[^/]+$", { "domain": { "name": "a.com" } }),
        ]))
        await calls(
            vercel.check("a.com"), vercel.buy("a.com", 1, CONTACT), vercel.get("a.com"), vercel.records("a.com"),
            vercel.set("a.com", "A", "www", "1.2.3.4", 60), vercel.unset("a.com", "r1"), vercel.verify("www.a.com"),
            vercel.delete("www.a.com"),
        )

        expect(len(seen)).above(9)
        expect(checked(loaded("vercel.json"), seen)).equals([])

        seen.clear()

        flare = Domains()
        price = { "currency": "USD", "registration_cost": "9.15", "renewal_cost": "9.15" }
        offer = { "domains": [{ "name": "a.com", "registrable": True, "pricing": price }] }

        flare.connect("cloudflare", token="t", account="acc1", zone="z1", transport=recorder(seen, [
            (r"/domain-check$", { "result": offer }),
            (r"/zones$", { "result": [{ "id": "z1", "name": "a.com" }] }), (r"/dns_records$", { "result": [] }),
            (r"/custom_hostnames$", { "result": [] }), (r".", { "result": {} }),
        ]))
        await calls(
            flare.check("a.com"), flare.buy("a.com", 1, CONTACT), flare.get("a.com"), flare.records("a.com"),
            flare.set("a.com", "A", "www", "1.2.3.4", 60), flare.unset("a.com", "r1"), flare.verify("www.a.com"),
        )

        expect(len(seen)).above(9)
        expect(checked(loaded("cloudflare.json"), seen, "/client/v4")).equals([])

    async def test_whatsapp_and_gemini_bodies_follow_meta_and_google_definitions ( self ) -> None:

        seen: list[Ask] = []

        meta = WhatsApp("tok", "1099", transport=recorder(seen, [(r"/messages$", { "messages": [{ "id": "w1" }] })]))

        await calls(
            meta.send(Text.compose("hi").to("+201000000000"), ""),
            meta.send(Text.compose("").to("+201000000000").template("otp", "ar", "1234"), ""),
            meta.send(Text.compose("look").to("+201000000000").media("https://e.com/a.png"), ""),
        )

        expect(len(seen)).equals(3)
        expect(checked(loaded("whatsapp.yaml"), seen)).equals([])

        seen.clear()

        google = loaded("gemini.json")
        gem    = Gemini(Model("gemini-x", key="k"), recorder(seen, [(r":generate", { "candidates": [] })]))
        parts  = (Attachment("a.png", b"\x89PNG", "image/png"), Attachment("d.pdf", b"%PDF", "application/pdf"))

        await calls(gem.complete(
            [Message.system("s"), Message.user("hi", *parts)],
            Options(
                temperature=0.2, max_tokens=50, top_p=0.9, stop=("END",), json=True, top_k=4, seed=3, presence=0.1,
                frequency=0.1, effort="low",
            ),
        ))

        await calls(gem.complete([Message.user("hi")], Options(schema=ANSWER)))

        rows    = { "embeddings": [{ "values": [0.1, 0.2] }, { "values": [0.3, 0.4] }] }
        vectors = Gemini(Model("gemini-embedding-001", key="k"), recorder(seen, [(r":batchEmbed", rows)]))

        await calls(vectors.embed(["refunds", "shipping"], query=True))

        methods = google["resources"]["models"]["methods"]

        for asked, action, model in zip(seen, ("generateContent", "generateContent", "batchEmbedContents"), (
            "gemini-x", "gemini-x", "gemini-embedding-001",
        ), strict=True):

            method = methods[action]

            expect(urlsplit(asked.url).path.removeprefix("/")).equals(method["flatPath"].replace("{modelsId}", model))
            expect(undeclared(google["schemas"], method["request"]["$ref"], json.loads(asked.body))).equals([])

        expect(json.loads(seen[1].body)["generationConfig"]).keys("responseMimeType", "responseJsonSchema")
        expect(json.loads(seen[2].body)["requests"][0]).subset({ "taskType": "RETRIEVAL_QUERY" })

def camel ( name: str ) -> str:

    head, *rest = name.split("_")

    return head + "".join(part.title() for part in rest)

def undeclared ( schemas: Mapping[str, Any], ref: str, body: Mapping[str, Any], trail: str = "" ) -> list[str]:

    known = schemas.get(ref, {}).get("properties", {})
    found: list[str] = []

    for key, value in body.items():

        field = known.get(key) or known.get(camel(key))

        if field is None:

            found.append(f"{trail}{key} is not a {ref} field")

            continue

        inner = field.get("$ref") or (field.get("items") or {}).get("$ref")
        items = value if isinstance(value, list) else [value]

        found.extend(
            note for item in items if inner and isinstance(item, Mapping)
            for note in undeclared(schemas, inner, item, f"{trail}{key}.")
        )

    return found
