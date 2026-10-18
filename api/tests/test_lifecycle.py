from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from starlette.websockets import WebSocketState
from core.broadcast import Broadcast
from core.cache import Cache, MemoryStore, cache
from core.date import UTC, DateTime
from core.error import Code, Fault
from core.event import Event, Events
from core.health import Health, Result
from core.queue import MemoryDriver, Queue
from core.schedule import Cron, Schedule
from core.socket import Connection, Frame, Limits, Socket
import asyncio, pytest

@dataclass(frozen=True, slots=True)
class Rang(Event):

    n : int

@dataclass(frozen=True, slots=True)
class Person:

    id : str

class StubSocket:

    client_state = WebSocketState.CONNECTED

    def __init__ ( self ) -> None:

        self.sent: list[bytes] = []
        self.closed: tuple[int, str | None] | None = None

    async def send_bytes ( self, data: bytes ) -> None:
        self.sent.append(data)

    async def receive ( self ) -> Mapping[str, Any]:
        return { "type": "websocket.disconnect", "code": 1000 }

    async def close ( self, code: int = 1000, reason: str | None = None ) -> None:
        self.closed = (code, reason)

@pytest.mark.anyio
class TestCache:

    async def test_locks_tags_and_atomic_verbs ( self ) -> None:

        store = Cache(MemoryStore())
        loads: list[int] = []

        async def load () -> int:

            loads.append(1)

            return 9

        assert await store.add("k", 1) and not await store.add("k", 2) and await store.get("k") == 1
        assert await store.pull("k") == 1 and await store.missing("k") and await store.pull("k", 0) == 0
        assert await store.set_many({ "a": 1, "b": 2 }, ttl=30) == 2
        assert await store.many(["a", "b", "c"]) == { "a": 1, "b": 2, "c": None }
        assert await store.forget_many("a", "b") == 2
        assert await store.decrement("n", 2) == -2 and await store.ttl("n") is None
        assert await store.remember_forever("f", load) == 9 and await store.remember_forever("f", load) == 9
        assert loads == [1] and await store.ttl("f") is None

        await store.set("t", 1, ttl=5)

        assert await store.touch("t", 60) and (await store.ttl("t") or 0) > 5 and not await store.touch("nope", 1)

        lock  = store.lock("job", ttl=5)
        other = store.lock("job", ttl=5)

        assert await lock.acquire() and lock.owned() and not await other.acquire() and lock.key() == "lock:job"
        assert await lock.holder() == lock.owner() and await lock.extend(10) and not await other.extend()

        with pytest.raises(Fault) as busy: await other.get(lambda: asyncio.sleep(0))

        assert busy.value.code == Code.CONFLICT and not await other.release()
        assert await lock.release() and not lock.owned() and not await lock.release()
        assert await other.acquire(wait=0.0) and await other.force_release() and await lock.holder() is None

        async with store.lock("ctx") as held: assert held.owned()

        assert await store.lock("ctx").acquire()
        assert await store.lock("job", ttl=5).block(0.2, lambda: asyncio.sleep(0, "ran")) == "ran"

        tagged = store.tags("users", "roles")

        await tagged.set("list", [1, 2], ttl=60)

        assert tagged.names() == ("roles", "users") and await tagged.get("list") == [1, 2] and await tagged.has("list")
        assert await tagged.increment("n") == 1 and await tagged.add("n", 5) is False and await tagged.pull("n") == 1
        assert await tagged.remember("r", 60, load) == 9 and await tagged.remember("r", 60, load) == 9
        assert loads == [1, 1]
        assert await store.tags("roles").flush() == 1
        assert await tagged.get("list") is None and not await tagged.has("r") and await tagged.forget("list") is False
        assert store.stats()["hits"] >= 1 and store.describe()["store"] == "memory" and store.name() == "memory"

        pulls: list[int] = []

        async def slow_load () -> int:

            pulls.append(1)

            return len(pulls)

        first = await store.flexible("swr", fresh=0.05, stale=60, load=slow_load)

        assert first == 1 and await store.flexible("swr", fresh=0.05, stale=60, load=slow_load) == 1

        await asyncio.sleep(0.06)

        assert await store.flexible("swr", fresh=0.05, stale=60, load=slow_load) == 1

        await asyncio.sleep(0.01)

        assert await store.get("swr") == 2 and len(pulls) == 2

@pytest.mark.anyio
class TestQueue:

    async def test_workers_pause_resume_and_failed_jobs_can_be_retried ( self ) -> None:

        own   = Queue()
        calls: list[int] = []
        done: list[str] = []

        async def boom ( value: int ) -> None:

            calls.append(value)

            if value < 0: raise RuntimeError("negative")

        own.setup(MemoryDriver(), ("default", "slow"), tries=1, backoff=0.0)
        own.on_success(lambda job: done.append(job.short()))

        task = own.task(boom)

        await task.on("slow").later(1)

        assert await own.sizes() == { "default": 0, "slow": 1 } and own.queues() == ("default", "slow")

        await own.push(boom, -1)

        assert await own.drain() == 2 and sorted(calls) == [-1, 1] and done == ["boom"]

        failed = own.failed()

        assert len(failed) == 1 and failed[0].error == "RuntimeError" and failed[0].job.short() == "boom"
        assert failed[0].dump()["reason"] == "negative" and own.stats()["buried"] == 1
        assert await own.retry_failed() == 1 and own.failed() == [] and await own.size() == 1
        assert await own.drain() == 1 and len(own.failed()) == 1 and own.flush_failed() == 1 and own.failed() == []
        assert await own.bulk(boom, [(2,), (3,)]) == 2 and await own.size() == 2
        assert await task.delayed(0.01).later(4) and (await own.sizes())["default"] == 3

        assert own.start(1) == 2 and not own.paused() and own.pause() and own.paused() and not own.pause()

        await asyncio.sleep(0.05)

        assert await own.size() == 3 and own.describe()["paused"] is True and own.resume() and not own.resume()

        for _ in range(100):

            if await own.size() == 0 and len(calls) == 6: break

            await asyncio.sleep(0.02)

        assert sorted(calls[-3:]) == [2, 3, 4] and own.describe()["workers"] == 2
        assert await own.stop() == 2 and own.stats()["workers"] == 0 and await own.stop() == 0
        assert await own.clear_all() == 0

        order: list[str] = []

        async def first ( tag: str ) -> None:
            order.append(f"first:{tag}")

        def second ( tag: str, times: int = 1 ) -> None:
            order.extend([f"second:{tag}"] * times)

        linked = await own.chain([(first, ("a",)), (second, ("b",), { "times": 2 }), (first, ("c",))], queue="slow")
        spread = await own.batch([(first, ("x",)), (first, ("y",))])

        assert linked.queue == "slow" and len(spread) == 2 and await own.size("slow") == 1 and await own.size() == 2
        assert await own.drain("slow") == 1 and order == ["first:a", "second:b", "second:b", "first:c"]
        assert await own.drain() == 2 and sorted(order[-2:]) == ["first:x", "first:y"]

        await own.chain([(boom, (-5,)), (first, ("never",))])

        assert await own.drain() == 1 and len(own.failed()) == 1 and "never" not in "".join(order)

        once  = await own.push_unique("report", first, "u1", unique_for=30)
        twice = await own.push_unique("report", first, "u2", unique_for=30)

        assert once is not None and once.unique == "report" and twice is None and own.stats()["skipped"] == 1
        assert await own.drain() == 1 and order[-1] == "first:u1"
        assert (await own.push_unique("report", first, "u3", unique_for=30)) is not None and await own.drain() == 1

        await own.close()

class TestSchedule:

    def test_cron_next_task_pausing_and_upcoming ( self ) -> None:

        cron  = Cron("*/15 2 * * mon-fri")
        after = DateTime(2026, 10, 16, 2, 20, tzinfo=UTC)
        table = Schedule()
        ran: list[str] = []

        assert cron.next(after) == DateTime(2026, 10, 16, 2, 30, tzinfo=UTC)
        assert cron.next(DateTime(2026, 10, 16, 2, 45, tzinfo=UTC)) == DateTime(2026, 10, 19, 2, 0, tzinfo=UTC)
        assert [moment.month for moment in Cron("@monthly").upcoming(after, 2)] == [11, 12]
        assert Cron("0 9 * * *").with_weekdays("1-5").parts[4] == "1-5"
        assert cron.describe()["weekdays"] == [1, 2, 3, 4, 5]
        assert Cron("0 0 1 jan,jul *").months == frozenset({ 1, 7 })

        quick = table.call(lambda: ran.append("q"), "quick").every(60)
        night = table.call(lambda: ran.append("n"), "night").daily_at("03:00").weekdays().description("nightly")
        now   = DateTime(2026, 10, 19, 3, 0, tzinfo=UTC)

        assert night.cron is not None and night.cron.expression == "0 3 * * 1-5" and night.due(now)
        assert not night.due(DateTime(2026, 10, 18, 3, 0, tzinfo=UTC))
        assert table.pause("night") == 1 and not night.due(now) and [task.name for task in table.due(now)] == ["quick"]
        assert table.resume() == 2 and table.has("night") and table.names() == ["quick", "night"]
        assert quick.next_run(now) == now
        assert night.next_run(DateTime(2026, 10, 17, tzinfo=UTC)) == DateTime(2026, 10, 19, 3, 0, tzinfo=UTC)
        assert [slot["task"] for slot in table.upcoming(2, now)] == ["quick", "night"]
        assert table.call(lambda: None, "noon").twice_daily(6, 18).weekends().cron is not None
        noon = table.find("noon").cron

        assert noon is not None and noon.expression == "0 6,18 * * 0,6"
        assert table.forget("quick") and not table.has("quick") and night.dump()["note"] == "nightly"
        eom = table.call(lambda: None, "eom").last_day_of_month("23:00").cron

        assert eom is not None and eom.expression == "0 23 28-31 * *"
        assert table.call(lambda: None, "office").every(1).between("00:00", "23:59").inside("00:00", "23:59")
        midweek = table.call(lambda: None, "mw").daily_at("08:00").on_days("mon", "wed").cron

        assert midweek is not None and midweek.parts[4] == "1,3"
        assert not table.find("office").inside("23:58", "23:59") or table.find("office").inside("23:59", "00:01")
        assert table.describe()["tasks"] == 5 and not table.running()

        with pytest.raises(Fault): table.call(lambda: None, "bad").every(0)

    @pytest.mark.anyio
    async def test_tasks_run_hooks_filters_and_one_server_locks ( self ) -> None:

        table  = Schedule()
        events: list[str] = []

        async def work () -> None:
            events.append("work")

        task = table.call(work, "work").every(1).when(lambda: True).skip(lambda: False)

        task.before(lambda _: events.append("before")).after(lambda _: events.append("after"))
        task.on_success(lambda _: events.append("ok"))

        assert await task.run() and events == ["before", "work", "after", "ok"] and task.runs == 1

        task.when(lambda: False)

        assert not await task.run() and task.skipped == 1 and await table.run("work")

        flaky = table.call(lambda: 1 // 0, "flaky").every(1).on_failure(lambda _: events.append("fail"))

        assert not await flaky.run() and flaky.failures == 1 and flaky.last_error == "ZeroDivisionError"
        assert events[-1] == "fail" and flaky.dump()["error"] == "ZeroDivisionError"

        single = table.call(work, "single").every(1).on_one_server(lock_ttl=5)
        held   = cache.lock("schedule:single", 5)

        assert await held.acquire() and not await single.run() and single.skipped == 1

        await held.release()

        assert await single.run() and single.runs == 1 and await table.run_due(DateTime(2030, 1, 1, tzinfo=UTC))

@pytest.mark.anyio
class TestEvents:

    async def test_once_pause_record_history_and_off ( self ) -> None:

        bus  = Events()
        seen: list[object] = []

        bus.listen(Rang, seen.append)
        bus.once(Rang, lambda event: seen.append(("once", event.n)))

        assert bus.has_listeners(Rang) and len(bus.listener_names(Rang)) == 1 and bus.kinds() == [Rang.kind]
        assert await bus.dispatch(Rang(1)) == 1 and seen == [Rang(1), ("once", 1)]
        assert await bus.dispatch(Rang(2)) == 1 and seen[-1] == Rang(2)
        assert bus.pause() and not bus.pause() and bus.paused()
        assert await bus.dispatch(Rang(3)) == 0 and seen[-1] == Rang(2)
        assert await bus.resume() == 1 and seen[-1] == Rang(3) and not bus.paused() and await bus.resume() == 0

        with bus.record() as recorded: await bus.dispatch(Rang(4))

        assert recorded == [Rang(4)] and [item["kind"] for item in bus.history(2)] == [Rang.kind] * 2
        assert await bus.dispatch_many([Rang(5), Rang(6)]) == 2 and len(bus.history()) == 6
        assert await bus.dispatch_if(False, Rang(9)) == 0 and await bus.dispatch_unless(True, Rang(9)) == 0
        assert await bus.dispatch_if(True, Rang(8)) == 1 and seen[-1] == Rang(8)
        assert bus.off(Rang, seen.append) and not bus.off(Rang, seen.append) and await bus.dispatch(Rang(7)) == 0
        assert bus.describe()["dispatched"] == 8 and Rang.kind in Event.kinds() and not bus.has_listeners(Rang)

@pytest.mark.anyio
class TestSocketHub:

    async def test_hub_broadcasts_kicks_tracks_users_and_broadcast_targets ( self ) -> None:

        hub = Socket()

        hub.setup(Limits(connections=2, queue=4, frame=256, ping=5.0, drops=2))

        first  = hub.attach(Connection("a", StubSocket(), user=Person("1")))
        second = hub.attach(Connection("b", StubSocket(), user=Person("2")))

        hub.join(first, "news")
        hub.join(second, "news")

        assert hub.full() and hub.publish("news", "x", 1) == 2 and hub.broadcast("hello") == 2
        assert hub.broadcast("hello", exclude="a") == 1 and hub.send_to_user("1", "dm", { "k": 1 }) == 1
        assert hub.connections_of("2") == [second] and first.emit("e") and first.describe()["user"] == "1"
        assert first.subscribed("news") and first.age() >= 0 and hub.describe()["limits"]["connections"] == 2
        assert await hub.kick("a") and not await hub.kick("a") and hub.stats()["connections"] == 1
        assert hub.subscribers("news") == 1 and first.closed and not first.emit("late")
        assert Frame.command('{"event": "ping"}').is_command()
        assert Frame("x").error(Fault(Code.FORBIDDEN, reason="r")).data == { "code": "forbidden", "reason": "r" }
        assert Frame.decode('{"event":"subscribe","data":{"auth":"t"}}').auth() == "t"

        with pytest.raises(Fault): Frame.command('{"event": "dance"}')

        live  = Broadcast()
        third = hub.attach(Connection("c", StubSocket(), user=Person("1")))

        live.setup(hub)
        live.public("news")
        live.channel("users.{user_id}", lambda user, user_id: str(user.id) == user_id)
        hub.join(third, "private-users.1")

        assert live.to_user("1").send("ping", 1) == 1 and live.to_everyone("all") == 2
        assert live.to("private-users.1").except_("c").send("x") == 0 and live.to("news").send_event(Rang(1)) == 1
        assert live.registry().forget("news") and live.channels() == ["users.{user_id}"]
        assert live.describe()["driver"] == "local" and live.kind("presence-x") == "presence"
        found = live.find("users.9")

        assert found is not None and found[1] == { "user_id": "9" }
        assert live.registry().all()[0].params() == ["user_id"]

        await live.start()
        await live.stop()

        assert await hub.close_all() == 2 and hub.channels() == {}

@pytest.mark.anyio
class TestHealth:

    async def test_checks_verdicts_tags_and_timeouts ( self ) -> None:

        board = Health()

        async def slow () -> bool:

            await asyncio.sleep(1)

            return True

        def broken () -> bool:
            raise RuntimeError("broken")

        board.register("db", lambda: True, tags=("ready", "live"))
        board.register("cache", lambda: Result.degraded("slow", hits=1), critical=False, tags=("ready",))
        board.register("mail", lambda: { "status": "ok", "sent": 3 }, critical=False)

        report = await board.report()

        assert report["status"] == "degraded" and report["checks"]["db"]["status"] == "ok"
        assert report["checks"]["cache"]["reason"] == "slow" and report["checks"]["mail"]["sent"] == 3
        assert board.failing(report) == ["cache"] and board.last() is report
        assert board.names() == ["cache", "db", "mail"]
        assert await board.alive() and not await board.ready() and await board.healthy(["db"])

        board.register("slow", slow, wait=0.05)
        board.register("broken", broken, critical=False)
        board.register("word", lambda: "flaky")

        report = await board.report()

        assert report["status"] == "down" and report["checks"]["slow"]["reason"] == "timeout"
        assert report["checks"]["broken"]["status"] == "down" and report["checks"]["word"]["reason"] == "flaky"
        assert (await board.run("db")).healthy() and board.forget("slow") and not board.forget("slow")
        assert board.has("db") and board.describe()["last"] == "down" and len(board.describe()["checks"]) == 5
        assert Result.of("degraded").status == "degraded" and Result.of(None).healthy()
        assert Result.of(False).status == "down"

        board.clear()

        assert (await board.report())["status"] == "ok" and board.names() == []
