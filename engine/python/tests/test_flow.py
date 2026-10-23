from typing import Annotated, Any, cast

from engine.error import Code, error
from engine.fast import Lru, Ttl
from engine.func import Policy, func
from engine.test import expect, test
from engine.thread import thread
from engine.validate import Email, Phone, Shape, field, rule, validate
import asyncio, pytest

class Signup(Shape):

    email  : Email
    phone  : Phone | None = None
    name   : Annotated[str, rule().string().trim().squish().between(2, 40)]
    age    : int = field(18, ge=13, le=120)
    invite : str = field("", alias=("invite", "code"))

class Ticks:

    def __init__ ( self ) -> None:

        self.now = 100.0

    def __call__ ( self ) -> float:

        return self.now

class TestMemory:

    def test_lru_evicts_least_recent_and_expires_per_entry ( self ) -> None:

        clock = Ticks()
        kept: Lru[str, int] = Lru(2, clock=clock)

        kept.set("a", 1)
        kept.set("b", 2, ttl=5)

        expect(kept.get("a")).equals(1)

        kept.set("c", 3)

        expect((kept.has("b"), kept.keys(), kept.stats()["evictions"])).equals((False, ["a", "c"], 1))

        kept.set("d", 4, ttl=5)
        clock.now += 6

        expect((kept.get("d"), kept.ttl("c"), kept.add("c", 9), kept.pop("c"), len(kept))).equals(
            (None, None, False, 3, 0),
        )
        expect(kept.remember("e", lambda: 5)).equals(5)
        expect(kept.stats()).subset({ "hits": 1, "misses": 2, "limit": 2 })

    def test_ttl_maps_are_bounded_by_a_limit ( self ) -> None:

        bounded: Ttl[str, int] = Ttl(sweep=100, limit=3)

        for index in range(5): bounded.set(f"k{index}", index)

        expect((bounded.keys(), bounded.stats()["evictions"])).equals((["k2", "k3", "k4"], 2))

@pytest.mark.anyio
class TestCalls:

    async def test_memo_caches_sync_and_async_and_shares_one_flight ( self ) -> None:

        calls: list[int] = []

        @func.memo(ttl=60, size=2)
        def square ( value: int ) -> int:

            calls.append(value)

            return value * value

        @func.memo
        async def slow ( value: int ) -> int:

            calls.append(-value)

            await asyncio.sleep(0.01)

            return value + 1

        expect((square(3), square(3), square(4), square(5), square(3))).equals((9, 9, 16, 25, 9))
        expect(calls).equals([3, 4, 5, 3])
        expect(square.stats()).subset({ "size": 2, "evictions": 2 })
        expect((square.forget(3), square.forget(3), square.clear())).equals((True, False, 1))

        calls.clear()

        results = await asyncio.gather(*(slow(1) for _ in range(5)))

        expect((results, calls, slow.stats()["shared"])).equals(([2] * 5, [-1], 4))
        expect(await slow(1)).equals(2)
        expect(func.memo(len, size=1)(["ab", "c"])).equals(2)

        class Box:

            @func.memo
            def size ( self ) -> int:

                calls.append(99)

                return 3

        box = Box()

        expect((box.size(), box.size(), calls.count(99))).equals((3, 3, 1))

    async def test_retry_follows_an_explicit_safe_policy ( self ) -> None:

        attempts: list[str] = []

        async def flaky () -> str:

            attempts.append("x")

            if len(attempts) < 3: raise error.unavailable("upstream")

            return "done"

        async def unsure () -> str:

            attempts.append("t")

            raise error.timeout("llm")

        expect(await thread.retry(flaky, delay=0, jitter=True)).equals("done")
        expect(attempts).equals(["x", "x", "x"])

        attempts.clear()

        await test.rejects(thread.retry(unsure, delay=0), Code.UNAVAILABLE, "llm")

        expect(attempts).equals(["t"])

        attempts.clear()

        await test.rejects(thread.retry(unsure, Policy(times=2, delay=0, idempotent=True)), Code.UNAVAILABLE)

        expect(attempts).equals(["t", "t"])

        attempts.clear()

        async def refused () -> str:

            attempts.append("c")

            raise error.conflict("taken")

        await test.rejects(thread.retry(refused, delay=0), Code.CONFLICT, "taken")

        expect(attempts).equals(["c"])
        waits = func.policy(jitter=True, delay=1, backoff=2, times=4, cap=1.5).waits()

        expect(waits).length(3).each(lambda wait: 0 <= wait <= 1.5)

        with test.fails(Code.INTERNAL, "retry.times"): func.retry(flaky, times=0)

    async def test_timeouts_say_the_outcome_is_unknown ( self ) -> None:

        async def slow () -> int:

            await asyncio.sleep(1)

            return 1

        fault = await test.rejects(thread.timeout(slow(), 0.01, "provider"), Code.UNAVAILABLE, "provider")

        expect((fault.unknown, fault.safe(), fault.safe(idempotent=True))).equals((True, False, True))
        expect(await thread.wait_for(slow(), 0.01, -1)).equals(-1)

        await test.rejects(func.timeout(slow, 0.01, "wrapped")(), Code.UNAVAILABLE, "wrapped")

        def plain () -> int:

            return 1

        with test.fails(Code.INTERNAL, "timeout.sync"): func.timeout(cast("Any", plain), 0.01)

class TestRules:

    def test_the_rule_dsl_validates_alone_and_inside_shapes ( self ) -> None:

        name = rule().string().trim().squish().between(2, 10)

        expect((name.check("  Ann   Lee "), name.passes("x"), name.errors("x"))).equals(
            ("Ann Lee", False, ["Must be between 2 and 10"]),
        )
        expect((
            rule.text(1, 3).text(), rule.number(1, 9).spec(), rule.parse("required|email").passes("a@b.co"),
        )).equals(
            ("string|between:1,3", ["numeric", "min:1", "max:9"], True),
        )
        even = rule().integer().where(lambda value: int(value) % 2 == 0, "Must be even")

        expect(even.errors(3)).equals(["Must be even"])

        with test.fails(Code.VALIDATION, "age", field="age"): rule().integer().min(18).check(16, "age")

        signup = Signup.of({ "email": " ANN@X.IO ", "phone": "+٢٠١٠٠٠٠٠٠٠٠", "name": " Ann  ", "code": "vip" })

        expect(signup.dump()).equals({
            "email": "ann@x.io", "phone": "+20100000000", "name": "Ann", "age": 18, "invite": "vip",
        })
        expect((signup.given(), Signup.required(), signup.with_(age=30).only("age"))).satisfies(
            lambda found: set(found[0]) == { "email", "phone", "name", "invite" } and found[1] == ["email", "name"]
            and found[2] == { "age": 30 },
        )
        expect(Signup.json_schema()["properties"]["email"]).subset({ "format": "email", "maxLength": 254.0 })

        with test.fails(Code.VALIDATION) as caught: Signup.of({ "email": "nope", "name": "", "age": 7, "extra": 1 })

        expect(caught.fault).some().at("errors").keys("email", "name", "age", "extra")
        expect(validate.check(Email, " A@B.IO ")).equals("a@b.io")
