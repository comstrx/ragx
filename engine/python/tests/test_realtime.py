from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, override

from engine.broadcast import Broadcast
from engine.event import Event, events
from engine.error import Code, Fault
from engine.http import Request, Response, Route, http
from engine.socket import Connection, Frame, Limits, Socket
from engine.test import expect, test
import asyncio

@dataclass(frozen=True, slots=True)
class Person:

    id    : str
    name  : str
    roles : tuple[str, ...] = ()

    def has_role ( self, role: str ) -> bool:

        return role in self.roles

@dataclass(frozen=True, slots=True)
class Announced(Event):

    title : str

    @override
    def channels ( self ) -> Sequence[str]:

        return ("news", "private-staff")

PEOPLE = { "alice": Person("1", "Alice", ("admin",)), "bob": Person("2", "Bob") }

async def guard ( token: str | None ) -> Person:

    found = PEOPLE.get(token or "")

    if found is None: raise Fault(Code.UNAUTHORIZED, reason="token")

    return found

def wire () -> tuple[Socket, Broadcast, Any]:

    hub  = Socket()
    live = Broadcast()

    hub.setup(Limits(connections=3, queue=8, frame=256, ping=5.0, drops=2))
    live.setup(hub, guard=guard)
    live.public("news")
    live.channel("users.{user_id}", lambda user, user_id: user.id == user_id)
    live.channel("staff", lambda user: user.has_role("admin"))
    live.channel("room.{room}", lambda user, room: { "id": user.id, "name": user.name, "room": room })

    async def emit ( request: Request ) -> Response:

        body    = request.body()
        reached = live.emit(body["channel"], body["event"], body.get("data"), body.get("exclude"))

        return Response.ok({ "reached": reached })

    async def announce ( request: Request ) -> Response:

        body = request.body()

        return Response.ok({ "listeners": await events.dispatch(Announced(body["title"])) })

    app = http.build("Live", "0.0.1", [Route.group("", [Route.post("/emit", emit), Route.post("/announce", announce)])])

    app.socket("/ws", hub.endpoint, name="socket")

    return hub, live, app

class TestRealtime:

    def test_channels_authorize_fan_out_and_presence_over_a_live_socket ( self ) -> None:

        hub, _, app = wire()

        with test.sockets(app) as client, \
             client.connect("/ws?token=alice") as alice, \
             client.connect("/ws?token=bob") as bob, \
             client.connect("/ws") as guest:

            hello = alice.frames(1)[0]
            bobs  = bob.frames(1)[0]["data"]["socket_id"]

            expect(hello["event"]).equals("connected")
            expect(hello["data"]["ping"]).equals(5.0)
            expect(guest.frames(1)[0]["event"]).equals("connected")

            for session in (alice, bob, guest):
                session.send({ "event": "subscribe", "channel": "news", "id": "s1" })

            expect([session.frames(1)[0] for session in (alice, bob, guest)]).equals([
                { "event": "subscribed", "channel": "news", "data": { "channel": "news" }, "id": "s1" },
            ] * 3)
            expect(hub.subscribers("news")).equals(3)
            expect(hub.channels()).equals({ "news": 3 })

            reached = client.post("/emit", json={ "channel": "news", "event": "headline", "data": { "n": 1 } }).json()

            expect(reached["data"]["reached"]).equals(3)
            headline = { "event": "headline", "channel": "news", "data": { "n": 1 } }

            expect(alice.frames(1) == bob.frames(1) == [headline]).true()
            expect(guest.frames(1)[0]["data"]).equals({ "n": 1 })

            only = client.post("/emit", json={ "channel": "news", "event": "aside", "exclude": bobs }).json()

            expect(only["data"]["reached"]).equals(2)
            expect(alice.frames(1)[0]["event"]).equals("aside")
            expect(guest.frames(1)[0]["event"]).equals("aside")

            alice.send({ "event": "subscribe", "channel": "private-users.1" })
            bob.send({ "event": "subscribe", "channel": "private-users.1" })
            guest.send({ "event": "subscribe", "channel": "private-users.1" })
            guest.send({ "event": "subscribe", "channel": "private-nowhere" })

            expect(alice.frames(1)[0]["event"]).equals("subscribed")
            denied = { "event": "error", "data": { "code": "forbidden", "reason": "channel.denied" } }

            expect(bob.frames(1)[0]).equals(denied)
            reasons = [frame["data"]["reason"] for frame in guest.frames(2)]

            expect(reasons).equals(["channel.auth", "channel.private-nowhere.unknown"])

            alice.send({ "event": "subscribe", "channel": "presence-room.lobby" })

            expect(alice.frames(1)[0]["data"]["members"]).equals([{ "id": "1", "name": "Alice", "room": "lobby" }])

            bob.send({ "event": "subscribe", "channel": "presence-room.lobby" })

            joined = bob.frames(1)[0]
            seen   = alice.frames(1)[0]

            expect({ member["id"] for member in joined["data"]["members"] }).equals({ "1", "2" })
            expect(seen["event"]).equals("member_joined")
            expect(seen["data"]["member"]["name"]).equals("Bob")

            said    = { "event": "typing", "data": { "on": True } }
            whisper = { "event": "publish", "channel": "presence-room.lobby", "data": said }

            bob.send(whisper)

            typing = alice.frames(1)[0]

            expect(typing["event"]).equals("typing")
            expect(typing["data"]).equals(
                { "from": { "id": "2", "name": "Bob", "room": "lobby" }, "data": { "on": True } },
            )

            alice.send({ "event": "publish", "channel": "private-users.1", "data": { "event": "x" } })

            expect(alice.frames(1)[0]["data"]["reason"]).equals("channel.publish")

            bob.send({ "event": "unsubscribe", "channel": "presence-room.lobby", "id": "u1" })

            lobby = "presence-room.lobby"
            left  = { "event": "unsubscribed", "channel": lobby, "data": { "channel": lobby } }

            expect(bob.frames(1)[0]).equals({ **left, "id": "u1" })
            expect(alice.frames(1)[0]["event"]).equals("member_left")

            alice.send({ "event": "subscribe", "channel": "private-staff" })

            expect(alice.frames(1)[0]["event"]).equals("subscribed")

            told = client.post("/announce", json={ "title": "Launch" }).json()

            expect(told["data"]["listeners"]).equals(0)
            relayed = alice.frames(2)

            expect([frame["channel"] for frame in relayed]).equals(["news", "private-staff"])
            expect(relayed[0]).equals({ "event": "Announced", "channel": "news", "data": { "title": "Launch" } })

            alice.send({ "event": "ping", "id": "p1" })
            alice.send({ "event": "dance" })
            alice.text("not json")

            expect([frame["event"] for frame in alice.frames(3)]).equals(["pong", "error", "error"])
            expect(hub.stats()["connections"]).equals(3)
            expect(hub.stats()["published"] >= 6).true()

            expect(client.refused("/ws?token=alice")).equals(1013)

        expect(hub.stats()["connections"]).equals(0)
        expect(hub.channels()).equals({})

    def test_oversized_frames_close_the_socket_and_slow_consumers_are_shed ( self ) -> None:

        hub, _, app = wire()

        with test.sockets(app) as client, client.connect("/ws?token=alice") as alice:

            alice.frames(1)
            alice.text("x" * 300)

            expect(alice.closed()).equals(1009)

        async def shed () -> tuple[int, int, bool]:

            stub = test.stub()
            slow = hub.attach(Connection("slow", stub, outbox=asyncio.Queue(2)))

            hub.join(slow, "flood")

            for index in range(5): hub.publish("flood", "drip", index)

            await asyncio.sleep(0)

            return slow.dropped, hub.stats()["dropped"], slow.closed

        dropped, shed_total, closed = asyncio.run(shed())

        expect(dropped).equals(3)
        expect(shed_total).equals(3)
        expect(closed).is_(True)
        expect(Frame.decode(Frame("x", "c", { "k": 1 }, "7").encode())).equals(Frame("x", "c", { "k": 1 }, "7"))

        with test.fails(Code.BAD_REQUEST, "frame.event"): Frame.decode('{"event": ""}')
        with test.fails(Code.BAD_REQUEST, "frame"): Frame.decode("[1]")
