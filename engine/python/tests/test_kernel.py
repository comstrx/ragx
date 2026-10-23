from collections.abc import Mapping
from typing import ClassVar

from engine.cli import Cli, Command
from engine.config import Config, Env, Settings, field
from engine.context import Context, context
from engine.error import Bag, Code, Fault, error
from engine.exception import Exceptions, Handler, Target
from engine.log import log
from engine.test import Mismatch, expect, test
from engine.fs import Path
import asyncio, io, os, pickle, pytest

SCRUB = ("DEMO_NAME", "DEMO_PORT", "DEMO_TAGS", "DEMO_SECRET_KEY", "SHARED", "APP_ENV", "DEMO_TICK", "DEMO_RELEASE")

class Missing(LookupError):

    def __init__ ( self ) -> None:

        super().__init__("row")

class Mapped(Handler):

    maps   : ClassVar[Mapping[type[BaseException], Target]] = {
        ValueError  : Code.BAD_REQUEST,
        LookupError : lambda failure: Fault(Code.NOT_FOUND, reason=str(failure)),
        Missing     : Code.CONFLICT,
    }
    silent : ClassVar[tuple[type[BaseException], ...]] = (KeyError,)
    levels : ClassVar[Mapping[type[BaseException], str]] = { TimeoutError: "warning" }

class Demo(Settings, env_prefix="DEMO_"):

    name    : str = "demo"
    port    : int = field(1, ge=1, le=65535)
    tags    : list[str] = field(factory=list)
    release : str | None = None
    tick    : float = field(1.0, env="DEMO_CLOCK_TICK", gt=0)
    secret  : str = ""

class TestFaults:

    def test_codes_carry_status_message_family_and_parse_back ( self ) -> None:

        statuses = [200, 201, 202, 400, 401, 403, 404, 405, 409, 422, 429, 500, 503]

        expect([code.status() for code in Code]).equals(statuses)
        expect(Code.VALIDATION.message()).equals("The given data is invalid")
        expect((Code.of(404), Code.of(418), Code.of(599), Code.of(204))).equals(
            (Code.NOT_FOUND, Code.BAD_REQUEST, Code.INTERNAL, Code.OK),
        )
        expect((Code.parse("Not-Found"), Code.parse("nope"), Code.parse("nope", Code.CONFLICT))).equals(
            (Code.NOT_FOUND, None, Code.CONFLICT),
        )
        expect([code for code in Code if code.transient()]).equals([Code.TOO_MANY_REQUESTS, Code.UNAVAILABLE])
        expect((Code.CREATED.success(), Code.CONFLICT.client(), Code.UNAVAILABLE.server())).equals((True, True, True))
        expect(len(Code.failures())).equals(10)

    def test_faults_copy_immutably_round_trip_and_survive_pickling ( self ) -> None:

        fault = error.validation({ "email": ["taken"] }, reason="body")
        moved = fault.because("email").saying("Fix it").after(30).uncertain()
        back  = Fault.load(moved.dump())

        expect((fault.status, fault.reason, fault.retry_after, fault.unknown)).equals((422, "body", None, False))
        expect((moved.reason, moved.message, moved.retry_after, moved.unknown)).equals(("email", "Fix it", 30, True))
        expect(moved.__cause__).is_(fault)
        expect(back.dump()).equals(moved.dump()).at("errors.email.0").equals("taken")
        expect(pickle.loads(pickle.dumps(moved)).dump()).equals(moved.dump())
        expect((moved.first(), moved.first("email"), moved.first("name"), Fault(Code.OK).first())).equals(
            ("taken", "taken", None, None),
        )
        expect(repr(Fault(Code.NOT_FOUND, reason="user"))).equals("Fault(not_found, reason='user')")
        expect(Fault.load({ "status": 404 }).code).is_(Code.NOT_FOUND)

    def test_retry_safety_follows_transience_and_certainty ( self ) -> None:

        expect((error.unavailable().safe(), error.timeout().safe(), error.timeout().safe(idempotent=True))).equals(
            (True, False, True),
        )
        expect((error.conflict().safe(idempotent=True), error.too_many_requests(retry_after=2).retry_after)).equals(
            (False, 2),
        )
        expect(error.timeout("llm.claude").dump()).subset({ "code": "unavailable", "unknown": True, "status": 503 })
        expect(error.unsupported("gateway", "paytabs", "withdraw").dump()).subset({
            "code": "internal", "reason": "gateway.paytabs.unsupported.withdraw",
        })

    def test_throw_abort_and_ensure_raise_exactly_when_told ( self ) -> None:

        error.throw_if(False, Code.CONFLICT)
        error.throw_unless(True, Code.CONFLICT)
        error.abort_if(0, 403)

        expect(error.ensure(0, reason="zero")).equals(0)

        with test.fails(Code.NOT_FOUND, "user"): error.ensure(None, reason="user")
        with test.fails(Code.CONFLICT, "dup"): error.throw_if("yes", Code.CONFLICT, "dup")
        with test.fails(Code.FORBIDDEN, "owner"): error.abort_unless([], 403, "owner")
        with test.fails(Code.BAD_REQUEST) as caught: error.abort(418, "teapot")

        expect(caught.fault).some().at("status").equals(418)

        with test.fails(Code.VALIDATION, "email", field="email"): raise error.invalid("email", "taken")

    def test_bags_collect_field_messages_without_duplicates ( self ) -> None:

        bag = Bag({ "name": ["required"] }).add("name", "required", "short").add("email", "invalid")

        bag.merge({ "street": ["empty"] }, prefix="address").merge(Bag({ "email": ["taken"] }))

        expect(bag.dump()).equals({
            "name": ["required", "short"], "email": ["invalid", "taken"], "address.street": ["empty"],
        })
        expect((bag.count(), len(bag), bag.first(), bag.first("email"), bag.reason())).equals(
            (5, 5, "required", "invalid", "name"),
        )
        expect((bag.has("name", "email"), bag.has("name", "age"), bag.has_any("age", "email"))).equals(
            (True, False, True),
        )
        expect(bag.matching("address")).equals({ "address.street": ["empty"] })
        expect(("email" in bag, "age" in bag, list(bag))).equals((True, False, ["name", "email", "address.street"]))

        with test.fails(Code.VALIDATION, "name", field="address.street"): bag.throw()

        expect((bag.forget("name"), bag.forget("name"), bag.put("email", "one", "one").get("email"))).equals(
            (True, False, ["one"]),
        )
        expect((bag.clear(), bag.empty(), Bag().fault().errors)).equals((2, True, None))

        Bag().throw()

class TestHandlers:

    def test_handlers_map_by_the_most_specific_type_and_never_leak ( self ) -> None:

        handler = Mapped()

        expect(handler.fault_of(ValueError("x")).code).is_(Code.BAD_REQUEST)
        expect(handler.fault_of(KeyError("k")).dump()).subset({ "code": "not_found", "reason": "'k'" })
        expect(handler.fault_of(Missing()).code).is_(Code.CONFLICT)
        expect(handler.fault_of(RuntimeError("secret")).dump()).subset({
            "code": "internal", "message": "Something went wrong", "reason": "unexpected",
        })
        expect(handler.fault_of(RuntimeError("secret")).__cause__).instance_of(RuntimeError)
        expect((handler.quiet(KeyError()), handler.quiet(ValueError()))).equals((True, False))
        expect((handler.level_of(TimeoutError()), handler.level_of(ValueError()))).equals(("warning", None))

        handler.map(RuntimeError, Code.UNAVAILABLE)
        handler.silence(ValueError)
        handler.level(ValueError, "error")

        expect(handler.fault_of(RuntimeError()).code).is_(Code.UNAVAILABLE)
        expect(handler.describe()).subset({ "silent": ["KeyError", "ValueError"], "levels": { "ValueError": "error" } })
        expect(Mapped().fault_of(RuntimeError()).code).is_(Code.INTERNAL)

    def test_reports_reach_logs_callbacks_and_reporters_and_throttle_floods ( self ) -> None:

        log.setup("debug")

        facade = Exceptions()
        heard: list[str] = []
        calls: list[str] = []

        facade.use(Mapped())
        facade.reportable(LookupError, lambda failure: calls.append(type(failure).__name__))
        facade.on_report(lambda failure, fault, facts: heard.append(f"{fault.code}:{facts.get('path')}"))
        facade.on_report(lambda failure, fault, facts: 1 / 0)

        with test.logs("exception.unhandled", "exception.handled", "exception.reporter_failed") as caught:

            expect(facade.handle(RuntimeError("boom"), path="/x").code).is_(Code.INTERNAL)
            expect(facade.handle(TimeoutError(), path="/t").code).is_(Code.INTERNAL)
            expect(facade.handle(LookupError("gone")).reason).equals("gone")

        failed = [event for event in caught.events if event["event"] == "exception.unhandled"]

        expect(failed).length(1).at("0").subset({ "kind": "RuntimeError", "path": "/x", "level": "error" })
        expect(failed[0]).keys("exception")
        expect(heard).equals(["internal:/x", "internal:/t", "not_found:None"])
        expect(calls).equals(["LookupError"])

        with test.quiet("exception.handled", "exception.unhandled"): facade.handle(KeyError("hush"))

        facade.throttle(2, window=60)

        expect([facade.report(RuntimeError("flood")) for _ in range(5)]).equals([True, True, False, False, False])
        expect((facade.dropped(), facade.describe()["throttle"], facade.describe()["handler"])).equals((3, 2, "Mapped"))
        expect(facade.guard(lambda: int("x"), -1)).equals(-1)
        expect(facade.wrap(OSError("disk"), Code.UNAVAILABLE).code).is_(Code.UNAVAILABLE)

        log.setup("warning")

    @pytest.mark.anyio
    async def test_rescue_returns_defaults_for_async_failures ( self ) -> None:

        facade = Exceptions()

        async def broken () -> int:

            raise ValueError

        async def fine () -> int:

            return 7

        expect((await facade.rescue(broken, 0), await facade.rescue(fine, 0))).equals((0, 7))

        fault = await test.rejects(denied(), Code.CONFLICT)

        expect(fault.reason).equals("kept")

async def denied () -> int:

    raise Fault(Code.CONFLICT, reason="kept")

class TestContext:

    def test_slots_bind_restore_hide_and_carry_across_scopes ( self ) -> None:

        own = Context()

        own.put(tenant="acme", user="u1")
        own.hide("user")

        expect((own.get("tenant"), own.require("user"), own.get("nope", 3), own.has("nope"))).equals(
            ("acme", "u1", 3, False),
        )
        expect(own.snapshot()).equals({ "tenant": "acme" })
        expect(own.snapshot(hidden=True)).equals({ "tenant": "acme", "user": "u1" })
        expect((own.push("tags", "a"), own.push("tags", "b", "c"))).equals((["a"], ["a", "b", "c"]))
        expect((own.increment("hits"), own.increment("hits", 4))).equals((1, 5))

        with own.bind(tenant="beta"): expect(own.get("tenant")).equals("beta")

        expect(own.get("tenant")).equals("acme")

        with own.scope("request-0000001", job="mail") as request_id:

            expect((request_id, own.request_id(), own.get("job"))).equals(("request-0000001",) * 2 + ("mail",))

            carried = own.dump()

        expect((own.request_id(), own.has("job"))).equals((None, False))

        with own.load(carried) as restored: expect((restored, own.get("job"), own.get("user"))).equals(
            ("request-0000001", "mail", "u1"),
        )

        with own.scope("bad id!") as fresh: expect(fresh).matches(r"^[0-9a-f-]{36}$")

        expect((own.forget("tenant", "nope"), own.names())).equals((1, ["hits", "tags", "user"]))
        def inside () -> object:

            own.put(tenant="x")

            return own.get("tenant")

        expect(own.isolated(inside)).equals("x")
        expect(own.get("tenant")).none()

        with test.fails(Code.INTERNAL, "context.tenant"): own.require("tenant")

    def test_logs_correlate_request_ids_shared_slots_and_redact_secrets ( self ) -> None:

        log.setup("debug")

        with test.logs("probe") as caught, context.scope("trace-00000042"):

            log.share(tenant="acme")
            log.bind(service="mail").info(
                "probe", password="hunter2", url="postgres://tool:pw@db:5432/x", nested={ "api_key": "k" },
            )
            log.unshare("tenant")

        event = caught.events[0]

        expect(event).subset({
            "request_id": "trace-00000042", "tenant": "acme", "service": "mail", "password": "***",
            "url": "postgres://tool:***@db:5432/x", "nested": { "api_key": "***" }, "level": "info",
        })
        expect(log.bind(a=1).bind(b=2).unbind("a").fields()).equals({ "b": 2 })
        expect((log.enabled("debug"), log.level())).equals((True, "debug"))

        with test.logs("work") as spanned, log.span("work", job="j") as facts: facts["rows"] = 3

        expect(spanned.events[0]).subset({ "job": "j", "rows": 3, "level": "info" }).keys("ms")

        with test.logs("broken") as broken, test.raises(ZeroDivisionError), log.span("broken"): _ = 1 / 0

        expect(broken.events[0]).subset({ "outcome": "failed", "error": "ZeroDivisionError", "level": "error" })

        log.setup("warning")

        with test.quiet("hidden"): log.info("hidden")

    def test_expectations_fail_loudly_with_the_reason ( self ) -> None:

        with test.raises(Mismatch, "expected 2, got 1"): expect(1).equals(2)
        with test.raises(Mismatch, "a.b is missing"): expect({ "a": {} }).at("a.b")
        with test.raises(Mismatch, "x: expected 1, got 2"): expect({ "x": 2 }).subset({ "x": 1 })
        with test.raises(Mismatch, "expected a fault"), test.fails(Code.CONFLICT): pass
        with test.raises(Mismatch, "expected code conflict"), test.fails(Code.CONFLICT): error.throw(Code.NOT_FOUND)

        expect([1, 2, 3]).contains(1, 3).lacks(4).length(3).each(lambda item: item > 0).at("-1").equals(3)
        expect("hello").starts_with("he").ends_with("lo").matches("l+").instance_of(str)
        expect(0.1 + 0.2).near(0.3).between(0, 1).above(0).below(1)

class TestConfig:

    def test_env_layers_by_mode_and_typed_settings_with_aliases_and_faults ( self, tmp_path: Path ) -> None:

        (tmp_path / ".env").write_text("DEMO_NAME=base\nDEMO_PORT=10\nAPP_ENV=local\nSHARED=env\nDEMO_RELEASE=\n")
        (tmp_path / ".env.local").write_text('DEMO_NAME=local\nDEMO_TAGS=["a","b"]\nDEMO_CLOCK_TICK=2.5\n')
        (tmp_path / ".env.production").write_text("DEMO_NAME=production\n")
        (tmp_path / ".env.prod").write_text("DEMO_PORT=443\n")
        (tmp_path / ".secret").write_text("DEMO_SECRET=hidden\n")

        for key in SCRUB: os.environ.pop(key, None)

        own = Env()

        with own.scoped(SHARED="process"):

            expect(own.load(tmp_path)).equals("local")
            expect([path.name for path in own.loaded()]).equals([".env", ".env.local", ".secret"])
            expect((own.get("DEMO_NAME"), own.int("DEMO_PORT"), own.get("SHARED"), own.list("DEMO_TAGS"))).equals(
                ("local", 10, "process", ["a", "b"]),
            )
            expect((own.local(), own.production(), own.is_("testing", "local"), own.text("NOPE", "x"))).equals(
                (True, False, True, "x"),
            )

            settings = Config()
            demo     = settings.register("demo", Demo)

            expect(demo.dump()).equals({
                "name": "local", "port": 10, "tags": ["a", "b"], "release": None, "tick": 2.5, "secret": "hidden",
            })
            expect(demo.describe()).subset({ "secret": "***", "tick": 2.5 })
            expect(Demo.env_keys()).subset({ "port": "DEMO_PORT", "tick": "DEMO_CLOCK_TICK" })
            expect(settings.env_keys()).subset({ "demo.tick": "DEMO_CLOCK_TICK" })
            expect((settings.get("demo.name"), settings.get("demo.missing", "d"), settings.names())).equals(
                ("local", "d", ["demo"]),
            )
            expect(settings.register("demo", Demo)).is_(demo)
            expect(settings.of("demo", Demo)).is_(demo)

            with settings.scoped(demo__name="scoped"): expect(settings.get("demo.name")).equals("scoped")

            settings.set("demo.port", 99)

            expect((settings.get("demo.port"), settings.all()["demo"]["port"], settings.integer("demo.port"))).equals(
                (99, 99, 99),
            )
            expect((settings.remove("demo.port"), settings.remove("demo.port"), settings.get("demo.port"))).equals(
                (True, False, 10),
            )
            expect(settings.register("demo", Demo, port=7).port).equals(7)

            with test.fails(Code.INTERNAL, "config.demo.nothing"): settings.require("demo.nothing")
            with test.fails(Code.INTERNAL, "config.Demo", field="DEMO_PORT") as caught: Demo.load(port=0)

            expect(caught.fault).some().at("message").equals("The configuration is invalid")

            with test.fails(Code.INTERNAL, "validate.field.shade"): field(1, shade="red")

        for key in SCRUB: os.environ.pop(key, None)

        production = Env()

        expect(production.load(tmp_path, "production")).equals("production")
        expect([path.name for path in production.loaded()]).equals([".env", ".env.production", ".env.prod", ".secret"])
        expect((production.get("DEMO_NAME"), production.int("DEMO_PORT"), production.production())).equals(
            ("production", 443, True),
        )

        production.set("DEMO_PORT", 8)

        expect((production.int("DEMO_PORT"), production.remove("DEMO_PORT"))).equals((8, True))

        with test.fails(Code.INTERNAL, "env.DEMO_PORT"): production.require("DEMO_PORT")

        for key in SCRUB: os.environ.pop(key, None)

class TestCli:

    def test_commands_parse_typed_inputs_help_suggest_and_exit_with_meaning ( self ) -> None:

        out, err = io.StringIO(), io.StringIO()
        seen: list[tuple[str, object]] = []

        def greet ( name: str, times: int, loud: bool, tone: str | None ) -> int:

            seen.append(("greet", (name, times, loud, tone)))

            return 0

        async def drop ( table: str, force: bool ) -> int:

            await asyncio.sleep(0)

            if not force: raise Fault(Code.FORBIDDEN, "needs --force", "drop.force")

            seen.append(("drop", table))

            return 0

        cli = Cli("tool", "The tool", "1.2.3", default="greet", out=out, err=err).add(
            Command("greet", greet, "Say hello", "talk").argument("name", str, "world", "who")
                .option("times", int, 1, "how often", short="-t").flag("loud", "shout").option("tone")
                .alias("hi").example("tool greet ann -t 2"),
            Command("drop", drop, "Drop a table", "data").argument("table").flag("force", "really"),
        )

        expect([
            cli.run([]), cli.run(["hi", "ann", "-t", "3", "--loud"]), cli.run(["greet", "--tone", "dry"]),
            cli.run(["drop", "users", "--force"]),
        ]).equals([0, 0, 0, 0])
        expect(seen).equals([
            ("greet", ("world", 1, False, None)), ("greet", ("ann", 3, True, None)),
            ("greet", ("world", 1, False, "dry")), ("drop", "users"),
        ])
        refused = [cli.run(["grete"]), cli.run(["drop"]), cli.run(["greet", "-t", "x"]), cli.run(["greet", "--quiet"])]

        expect(refused).equals([2, 2, 2, 2])
        expect(err.getvalue()).contains(
            "Unknown command 'grete'. Did you mean 'greet'?", "the following arguments are required: table",
            "invalid int value: 'x'", "unrecognized arguments: --quiet",
        )
        expect(cli.run(["drop", "users"])).equals(1)
        expect(err.getvalue()).contains("drop: drop.force: needs --force")
        expect([cli.run(["help"]), cli.run(["greet", "--help"]), cli.run(["-V"])]).equals([0, 0, 0])
        expect(out.getvalue()).contains(
            "tool 1.2.3", "talk:\n  greet [name] -t, --times <int> --loud --tone <str>   Say hello",
            "data:\n  drop <table>", "Usage: tool greet [name]", "Aliases: hi", "tool greet ann -t 2",
            "-t, --times <int>   how often (default: 1)",
        )
        expect((cli.names(), test.some(cli.find("hi")).name)).equals((["drop", "greet"], "greet"))

        with test.fails(Code.INTERNAL, "cli.taken"): cli.add(Command("hi", greet))
        with test.fails(Code.INTERNAL, "cli.kind"): Command("x", greet).argument("n", list)
        with test.fails(Code.INTERNAL, "cli.duplicate"): Command("x", greet).flag("a").flag("a")
        with test.fails(Code.INTERNAL, "cli.order"): Command("x", greet).argument("a", str, "").argument("b")
