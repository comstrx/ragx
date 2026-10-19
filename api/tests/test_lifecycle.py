from dataclasses import dataclass

from core.broadcast import Broadcast
from core.cache import Cache, MemoryStore, cache
from core.date import UTC, DateTime
from core.error import Code, Fault
from core.event import Event, Events
from core.health import Health, Result
from core.queue import MemoryDriver, Queue
from core.schedule import Cron, Schedule
from core.socket import Connection, Frame, Limits, Socket
from core.test import expect, test
import asyncio, pytest

@dataclass(frozen=True, slots=True)
class Rang(Event):

    n : int

@dataclass(frozen=True, slots=True)
class Person:

    id : str

@pytest.mark.anyio
class TestCache:

    async def test_locks_tags_and_atomic_verbs ( self ) -> None:

        store = Cache(MemoryStore())
        loads: list[int] = []

        async def load () -> int:

            loads.append(1)

            return 9

        expect(await store.add("k", 1)).truthy()
        expect(await store.add("k", 2)).falsy()
        expect(await store.get("k")).equals(1)
        expect(await store.pull("k")).equals(1)
        expect(await store.missing("k")).truthy()
        expect(await store.pull("k", 0)).equals(0)
        expect(await store.set_many({ "a": 1, "b": 2 }, ttl=30)).equals(2)
        expect(await store.many(["a", "b", "c"])).equals({ "a": 1, "b": 2, "c": None })
        expect(await store.forget_many("a", "b")).equals(2)
        expect(await store.decrement("n", 2)).equals(-2)
        expect(await store.ttl("n")).none()
        expect(await store.remember_forever("f", load)).equals(9)
        expect(await store.remember_forever("f", load)).equals(9)
        expect(loads).equals([1])
        expect(await store.ttl("f")).none()

        await store.set("t", 1, ttl=5)

        expect(await store.touch("t", 60)).truthy()
        expect(await store.ttl("t") or 0).above(5)
        expect(await store.touch("nope", 1)).falsy()

        lock  = store.lock("job", ttl=5)
        other = store.lock("job", ttl=5)

        expect(await lock.acquire()).truthy()
        expect(lock.owned()).truthy()
        expect(await other.acquire()).falsy()
        expect(lock.key()).equals("lock:job")
        expect(await lock.holder()).equals(lock.owner())
        expect(await lock.extend(10)).truthy()
        expect(await other.extend()).falsy()

        await test.rejects(other.get(lambda: asyncio.sleep(0)), Code.CONFLICT, "lock.busy")
        expect(await other.release()).falsy()
        expect(await lock.release()).truthy()
        expect(lock.owned()).falsy()
        expect(await lock.release()).falsy()
        expect(await other.acquire(wait=0.0)).truthy()
        expect(await other.force_release()).truthy()
        expect(await lock.holder()).none()

        async with store.lock("ctx") as held: expect(held.owned()).truthy()

        expect(await store.lock("ctx").acquire()).truthy()
        expect(await store.lock("job", ttl=5).block(0.2, lambda: asyncio.sleep(0, "ran"))).equals("ran")

        tagged = store.tags("users", "roles")

        await tagged.set("list", [1, 2], ttl=60)

        expect(tagged.names()).equals(("roles", "users"))
        expect(await tagged.get("list")).equals([1, 2])
        expect(await tagged.has("list")).truthy()
        expect(await tagged.increment("n")).equals(1)
        expect(await tagged.add("n", 5)).is_(False)
        expect(await tagged.pull("n")).equals(1)
        expect(await tagged.remember("r", 60, load)).equals(9)
        expect(await tagged.remember("r", 60, load)).equals(9)
        expect(loads).equals([1, 1])
        expect(await store.tags("roles").flush()).equals(1)
        expect(await tagged.get("list")).none()
        expect(await tagged.has("r")).falsy()
        expect(await tagged.forget("list")).is_(False)
        expect(store.stats()["hits"] >= 1).true()
        expect(store.describe()["store"]).equals("memory")
        expect(store.name()).equals("memory")

        pulls: list[int] = []

        async def slow_load () -> int:

            pulls.append(1)

            return len(pulls)

        first = await store.flexible("swr", fresh=0.05, stale=60, load=slow_load)

        expect(first).equals(1)
        expect(await store.flexible("swr", fresh=0.05, stale=60, load=slow_load)).equals(1)

        await asyncio.sleep(0.06)

        expect(await store.flexible("swr", fresh=0.05, stale=60, load=slow_load)).equals(1)

        await asyncio.sleep(0.01)

        expect(await store.get("swr")).equals(2)
        expect(len(pulls)).equals(2)

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

        expect(await own.sizes()).equals({ "default": 0, "slow": 1 })
        expect(own.queues()).equals(("default", "slow"))

        await own.push(boom, -1)

        expect(await own.drain()).equals(2)
        expect(sorted(calls)).equals([-1, 1])
        expect(done).equals(["boom"])

        failed = own.failed()

        expect(len(failed)).equals(1)
        expect(failed[0].error).equals("RuntimeError")
        expect(failed[0].job.short()).equals("boom")
        expect(failed[0].dump()["reason"]).equals("negative")
        expect(own.stats()["buried"]).equals(1)
        expect(await own.retry_failed()).equals(1)
        expect(own.failed()).equals([])
        expect(await own.size()).equals(1)
        expect(await own.drain()).equals(1)
        expect(len(own.failed())).equals(1)
        expect(own.flush_failed()).equals(1)
        expect(own.failed()).equals([])
        expect(await own.bulk(boom, [(2,), (3,)])).equals(2)
        expect(await own.size()).equals(2)
        expect((await task.delayed(0.01).later(4)).queue).equals("default")
        expect((await own.sizes())["default"]).equals(3)

        expect(own.start(1)).equals(2)
        expect(own.paused()).falsy()
        expect(own.pause()).truthy()
        expect(own.paused()).truthy()
        expect(own.pause()).falsy()

        await asyncio.sleep(0.05)

        expect(await own.size()).equals(3)
        expect(own.describe()["paused"]).is_(True)
        expect(own.resume()).truthy()
        expect(own.resume()).falsy()

        for _ in range(100):

            if await own.size() == 0 and len(calls) == 6: break

            await asyncio.sleep(0.02)

        expect(sorted(calls[-3:])).equals([2, 3, 4])
        expect(own.describe()["workers"]).equals(2)
        expect(await own.stop()).equals(2)
        expect(own.stats()["workers"]).equals(0)
        expect(await own.stop()).equals(0)
        expect(await own.clear_all()).equals(0)

        order: list[str] = []

        async def first ( tag: str ) -> None:

            order.append(f"first:{tag}")

        def second ( tag: str, times: int = 1 ) -> None:

            order.extend([f"second:{tag}"] * times)

        linked = await own.chain([(first, ("a",)), (second, ("b",), { "times": 2 }), (first, ("c",))], queue="slow")
        spread = await own.batch([(first, ("x",)), (first, ("y",))])

        expect(linked.queue).equals("slow")
        expect(len(spread)).equals(2)
        expect(await own.size("slow")).equals(1)
        expect(await own.size()).equals(2)
        expect(await own.drain("slow")).equals(1)
        expect(order).equals(["first:a", "second:b", "second:b", "first:c"])
        expect(await own.drain()).equals(2)
        expect(sorted(order[-2:])).equals(["first:x", "first:y"])

        await own.chain([(boom, (-5,)), (first, ("never",))])

        expect(await own.drain()).equals(1)
        expect(len(own.failed())).equals(1)
        expect("".join(order)).lacks("never")

        once  = await own.push_unique("report", first, "u1", unique_for=30)
        twice = await own.push_unique("report", first, "u2", unique_for=30)

        once = test.some(once)
        expect(once.unique).equals("report")
        expect(twice).none()
        expect(own.stats()["skipped"]).equals(1)
        expect(await own.drain()).equals(1)
        expect(order[-1]).equals("first:u1")
        expect(await own.push_unique("report", first, "u3", unique_for=30)).some()
        expect(await own.drain()).equals(1)

        await own.close()

class TestSchedule:

    def test_cron_next_task_pausing_and_upcoming ( self ) -> None:

        cron  = Cron("*/15 2 * * mon-fri")
        after = DateTime(2026, 10, 16, 2, 20, tzinfo=UTC)
        table = Schedule()
        ran: list[str] = []

        expect(cron.next(after)).equals(DateTime(2026, 10, 16, 2, 30, tzinfo=UTC))
        expect(cron.next(DateTime(2026, 10, 16, 2, 45, tzinfo=UTC))).equals(DateTime(2026, 10, 19, 2, 0, tzinfo=UTC))
        expect([moment.month for moment in Cron("@monthly").upcoming(after, 2)]).equals([11, 12])
        expect(Cron("0 9 * * *").with_weekdays("1-5").parts[4]).equals("1-5")
        expect(cron.describe()["weekdays"]).equals([1, 2, 3, 4, 5])
        expect(Cron("0 0 1 jan,jul *").months).equals(frozenset({ 1, 7 }))

        quick = table.call(lambda: ran.append("q"), "quick").every(60)
        night = table.call(lambda: ran.append("n"), "night").daily_at("03:00").weekdays().description("nightly")
        now   = DateTime(2026, 10, 19, 3, 0, tzinfo=UTC)

        expect(test.some(night.cron).expression).equals("0 3 * * 1-5")
        expect(night.due(now)).truthy()
        expect(night.due(DateTime(2026, 10, 18, 3, 0, tzinfo=UTC))).falsy()
        expect(table.pause("night")).equals(1)
        expect(night.due(now)).falsy()
        expect([task.name for task in table.due(now)]).equals(["quick"])
        expect(table.resume()).equals(2)
        expect(table.has("night")).truthy()
        expect(table.names()).equals(["quick", "night"])
        expect(quick.next_run(now)).equals(now)
        expect(night.next_run(DateTime(2026, 10, 17, tzinfo=UTC))).equals(DateTime(2026, 10, 19, 3, 0, tzinfo=UTC))
        expect([slot["task"] for slot in table.upcoming(2, now)]).equals(["quick", "night"])
        expect(table.call(lambda: None, "noon").twice_daily(6, 18).weekends().cron).some()
        noon = table.find("noon").cron

        noon = test.some(noon)
        expect(noon.expression).equals("0 6,18 * * 0,6")
        expect(table.forget("quick")).truthy()
        expect(table.has("quick")).falsy()
        expect(night.dump()["note"]).equals("nightly")
        eom = table.call(lambda: None, "eom").last_day_of_month("23:00").cron

        eom = test.some(eom)
        expect(eom.expression).equals("0 23 28-31 * *")
        expect(table.call(lambda: None, "office").every(1).between("00:00", "23:59").inside("00:00", "23:59")).truthy()
        midweek = table.call(lambda: None, "mw").daily_at("08:00").on_days("mon", "wed").cron

        midweek = test.some(midweek)
        expect(midweek.parts[4]).equals("1,3")
        office = table.find("office")

        expect(not office.inside("23:58", "23:59") or office.inside("23:59", "00:01")).truthy()
        expect(table.describe()["tasks"]).equals(5)
        expect(table.running()).falsy()

        with test.fails(Code.INTERNAL, "schedule.interval"): table.call(lambda: None, "bad").every(0)

    @pytest.mark.anyio
    async def test_tasks_run_hooks_filters_and_one_server_locks ( self ) -> None:

        table  = Schedule()
        events: list[str] = []

        async def work () -> None:

            events.append("work")

        task = table.call(work, "work").every(1).when(lambda: True).skip(lambda: False)

        task.before(lambda _: events.append("before")).after(lambda _: events.append("after"))
        task.on_success(lambda _: events.append("ok"))

        expect(await task.run()).truthy()
        expect(events).equals(["before", "work", "after", "ok"])
        expect(task.runs).equals(1)

        task.when(lambda: False)

        expect(await task.run()).falsy()
        expect(task.skipped).equals(1)
        expect(await table.run("work")).truthy()

        flaky = table.call(lambda: 1 // 0, "flaky").every(1).on_failure(lambda _: events.append("fail"))

        expect(await flaky.run()).falsy()
        expect(flaky.failures).equals(1)
        expect(flaky.last_error).equals("ZeroDivisionError")
        expect(events[-1]).equals("fail")
        expect(flaky.dump()["error"]).equals("ZeroDivisionError")

        single = table.call(work, "single").every(1).on_one_server(lock_ttl=5)
        held   = cache.lock("schedule:single", 5)

        expect(await held.acquire()).truthy()
        expect(await single.run()).falsy()
        expect(single.skipped).equals(1)

        await held.release()

        expect(await single.run()).truthy()
        expect(single.runs).equals(1)
        expect(await table.run_due(DateTime(2030, 1, 1, tzinfo=UTC))).truthy()

@pytest.mark.anyio
class TestEvents:

    async def test_once_pause_record_history_and_off ( self ) -> None:

        bus  = Events()
        seen: list[object] = []

        bus.listen(Rang, seen.append)
        bus.once(Rang, lambda event: seen.append(("once", event.n)))

        expect(bus.has_listeners(Rang)).truthy()
        expect(len(bus.listener_names(Rang))).equals(1)
        expect(bus.kinds()).equals([Rang.kind])
        expect(await bus.dispatch(Rang(1))).equals(1)
        expect(seen).equals([Rang(1), ("once", 1)])
        expect(await bus.dispatch(Rang(2))).equals(1)
        expect(seen[-1]).equals(Rang(2))
        expect(bus.pause()).truthy()
        expect(bus.pause()).falsy()
        expect(bus.paused()).truthy()
        expect(await bus.dispatch(Rang(3))).equals(0)
        expect(seen[-1]).equals(Rang(2))
        expect(await bus.resume()).equals(1)
        expect(seen[-1]).equals(Rang(3))
        expect(bus.paused()).falsy()
        expect(await bus.resume()).equals(0)

        with bus.record() as recorded: await bus.dispatch(Rang(4))

        expect(recorded).equals([Rang(4)])
        expect([item["kind"] for item in bus.history(2)]).equals([Rang.kind] * 2)
        expect(await bus.dispatch_many([Rang(5), Rang(6)])).equals(2)
        expect(len(bus.history())).equals(6)
        expect(await bus.dispatch_if(False, Rang(9))).equals(0)
        expect(await bus.dispatch_unless(True, Rang(9))).equals(0)
        expect(await bus.dispatch_if(True, Rang(8))).equals(1)
        expect(seen[-1]).equals(Rang(8))
        expect(bus.off(Rang, seen.append)).truthy()
        expect(bus.off(Rang, seen.append)).falsy()
        expect(await bus.dispatch(Rang(7))).equals(0)
        expect(bus.describe()["dispatched"]).equals(8)
        expect(Event.kinds()).contains(Rang.kind)
        expect(bus.has_listeners(Rang)).falsy()

@pytest.mark.anyio
class TestSocketHub:

    async def test_hub_broadcasts_kicks_tracks_users_and_broadcast_targets ( self ) -> None:

        hub = Socket()

        hub.setup(Limits(connections=2, queue=4, frame=256, ping=5.0, drops=2))

        first  = hub.attach(Connection("a", test.stub(), user=Person("1")))
        second = hub.attach(Connection("b", test.stub(), user=Person("2")))

        hub.join(first, "news")
        hub.join(second, "news")

        expect(hub.full()).truthy()
        expect(hub.publish("news", "x", 1)).equals(2)
        expect(hub.broadcast("hello")).equals(2)
        expect(hub.broadcast("hello", exclude="a")).equals(1)
        expect(hub.send_to_user("1", "dm", { "k": 1 })).equals(1)
        expect(hub.connections_of("2")).equals([second])
        expect(first.emit("e")).truthy()
        expect(first.describe()["user"]).equals("1")
        expect(first.subscribed("news")).truthy()
        expect(first.age() >= 0).true()
        expect(hub.describe()["limits"]["connections"]).equals(2)
        expect(await hub.kick("a")).truthy()
        expect(await hub.kick("a")).falsy()
        expect(hub.stats()["connections"]).equals(1)
        expect(hub.subscribers("news")).equals(1)
        expect(first.closed).truthy()
        expect(first.emit("late")).falsy()
        expect(Frame.command('{"event": "ping"}').is_command()).truthy()
        expect(Frame("x").error(Fault(Code.FORBIDDEN, reason="r")).data).equals({ "code": "forbidden", "reason": "r" })
        expect(Frame.decode('{"event":"subscribe","data":{"auth":"t"}}').auth()).equals("t")

        with test.fails(Code.BAD_REQUEST, "frame.command"): Frame.command('{"event": "dance"}')

        live  = Broadcast()
        third = hub.attach(Connection("c", test.stub(), user=Person("1")))

        live.setup(hub)
        live.public("news")
        live.channel("users.{user_id}", lambda user, user_id: str(user.id) == user_id)
        hub.join(third, "private-users.1")

        expect(live.to_user("1").send("ping", 1)).equals(1)
        expect(live.to_everyone("all")).equals(2)
        expect(live.to("private-users.1").except_("c").send("x")).equals(0)
        expect(live.to("news").send_event(Rang(1))).equals(1)
        expect(live.registry().forget("news")).truthy()
        expect(live.channels()).equals(["users.{user_id}"])
        expect(live.describe()["driver"]).equals("local")
        expect(live.kind("presence-x")).equals("presence")
        found = live.find("users.9")

        found = test.some(found)
        expect(found[1]).equals({ "user_id": "9" })
        expect(live.registry().all()[0].params()).equals(["user_id"])

        await live.start()
        await live.stop()

        expect(await hub.close_all()).equals(2)
        expect(hub.channels()).equals({})

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

        expect(report["status"]).equals("degraded")
        expect(report["checks"]["db"]["status"]).equals("ok")
        expect(report["checks"]["cache"]["reason"]).equals("slow")
        expect(report["checks"]["mail"]["sent"]).equals(3)
        expect(board.failing(report)).equals(["cache"])
        expect(board.last()).is_(report)
        expect(board.names()).equals(["cache", "db", "mail"])
        expect(await board.alive()).truthy()
        expect(await board.ready()).falsy()
        expect(await board.healthy(["db"])).truthy()

        board.register("slow", slow, wait=0.05)
        board.register("broken", broken, critical=False)
        board.register("word", lambda: "flaky")

        report = await board.report()

        expect(report["status"]).equals("down")
        expect(report["checks"]["slow"]["reason"]).equals("timeout")
        expect(report["checks"]["broken"]["status"]).equals("down")
        expect(report["checks"]["word"]["reason"]).equals("flaky")
        expect((await board.run("db")).healthy()).truthy()
        expect(board.forget("slow")).truthy()
        expect(board.forget("slow")).falsy()
        expect(board.has("db")).truthy()
        expect(board.describe()["last"]).equals("down")
        expect(len(board.describe()["checks"])).equals(5)
        expect(Result.of("degraded").status).equals("degraded")
        expect(Result.of(None).healthy()).truthy()
        expect(Result.of(False).status).equals("down")

        board.clear()

        expect((await board.report())["status"]).equals("ok")
        expect(board.names()).equals([])
