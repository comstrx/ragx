from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from starlette.testclient import TestClient, WebSocketTestSession
from starlette.websockets import WebSocketDisconnect, WebSocketState
from core.broadcast import Broadcast
from core.event import Event, events
from core.exceptions import Code, Fault
from core.http import Request, Response, Route, http
from core.socket import Connection, Frame, Limits, Socket
import asyncio, pytest

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

    def channels ( self ) -> Sequence[str]:
        return ("news", "private-staff")

PEOPLE = { "alice": Person("1", "Alice", ("admin",)), "bob": Person("2", "Bob") }

async def guard ( token: str | None ) -> Person:

    found = PEOPLE.get(token or "")

    if found is None: raise Fault(Code.UNAUTHORIZED, reason="token")

    return found

class StubSocket:

    client_state = WebSocketState.CONNECTED

    def __init__ ( self ) -> None:

        self.sent: list[bytes] = []
        self.closed: tuple[int, str | None] | None = None

    async def send_bytes ( self, data: bytes ) -> None:
        self.sent.append(data)

    async def receive_text ( self ) -> str:
        return ""

    async def close ( self, code: int = 1000, reason: str | None = None ) -> None:
        self.closed = (code, reason)

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

        body = await request.json()

        reached = live.emit(body["channel"], body["event"], body.get("data"), body.get("exclude"))

        return Response.ok({ "reached": reached })

    async def announce ( request: Request ) -> Response:

        body = await request.json()

        return Response.ok({ "listeners": await events.dispatch(Announced(body["title"])) })

    app = http.build("Live", "0.0.1", [Route.group("", [Route.post("/emit", emit), Route.post("/announce", announce)])])

    app.add_api_websocket_route("/ws", hub.endpoint, name="socket")

    return hub, live, app

def frames ( session: WebSocketTestSession, count: int ) -> list[dict[str, Any]]:
    return [session.receive_json(mode="binary") for _ in range(count)]

class TestRealtime:

    def test_channels_authorize_fan_out_and_presence_over_a_live_socket ( self ) -> None:

        hub, _, app = wire()

        with TestClient(app) as client, \
             client.websocket_connect("/ws?token=alice") as alice, \
             client.websocket_connect("/ws?token=bob") as bob, \
             client.websocket_connect("/ws") as guest:

            hello = frames(alice, 1)[0]
            bobs  = frames(bob, 1)[0]["data"]["socket_id"]

            assert hello["event"] == "connected" and hello["data"]["ping"] == 5.0
            assert frames(guest, 1)[0]["event"] == "connected"

            for session in (alice, bob, guest):
                session.send_json({ "event": "subscribe", "channel": "news", "id": "s1" })

            assert [frames(session, 1)[0] for session in (alice, bob, guest)] == [
                { "event": "subscribed", "channel": "news", "data": { "channel": "news" }, "id": "s1" },
            ] * 3
            assert hub.subscribers("news") == 3 and hub.channels() == { "news": 3 }

            reached = client.post("/emit", json={ "channel": "news", "event": "headline", "data": { "n": 1 } }).json()

            assert reached["data"]["reached"] == 3
            headline = { "event": "headline", "channel": "news", "data": { "n": 1 } }

            assert frames(alice, 1) == frames(bob, 1) == [headline]
            assert frames(guest, 1)[0]["data"] == { "n": 1 }

            only = client.post("/emit", json={ "channel": "news", "event": "aside", "exclude": bobs }).json()

            assert only["data"]["reached"] == 2 and frames(alice, 1)[0]["event"] == "aside"
            assert frames(guest, 1)[0]["event"] == "aside"

            alice.send_json({ "event": "subscribe", "channel": "private-users.1" })
            bob.send_json({ "event": "subscribe", "channel": "private-users.1" })
            guest.send_json({ "event": "subscribe", "channel": "private-users.1" })
            guest.send_json({ "event": "subscribe", "channel": "private-nowhere" })

            assert frames(alice, 1)[0]["event"] == "subscribed"
            denied = { "event": "error", "data": { "code": "forbidden", "reason": "channel.denied" } }

            assert frames(bob, 1)[0] == denied
            reasons = [frame["data"]["reason"] for frame in frames(guest, 2)]

            assert reasons == ["channel.auth", "channel.private-nowhere.unknown"]

            alice.send_json({ "event": "subscribe", "channel": "presence-room.lobby" })

            assert frames(alice, 1)[0]["data"]["members"] == [{ "id": "1", "name": "Alice", "room": "lobby" }]

            bob.send_json({ "event": "subscribe", "channel": "presence-room.lobby" })

            joined = frames(bob, 1)[0]
            seen   = frames(alice, 1)[0]

            assert { member["id"] for member in joined["data"]["members"] } == { "1", "2" }
            assert seen["event"] == "member_joined" and seen["data"]["member"]["name"] == "Bob"

            said    = { "event": "typing", "data": { "on": True } }
            whisper = { "event": "publish", "channel": "presence-room.lobby", "data": said }

            bob.send_json(whisper)

            typing = frames(alice, 1)[0]

            assert typing["event"] == "typing"
            assert typing["data"] == { "from": { "id": "2", "name": "Bob", "room": "lobby" }, "data": { "on": True } }

            alice.send_json({ "event": "publish", "channel": "private-users.1", "data": { "event": "x" } })

            assert frames(alice, 1)[0]["data"]["reason"] == "channel.publish"

            bob.send_json({ "event": "unsubscribe", "channel": "presence-room.lobby", "id": "u1" })

            lobby = "presence-room.lobby"
            left  = { "event": "unsubscribed", "channel": lobby, "data": { "channel": lobby } }

            assert frames(bob, 1)[0] == { **left, "id": "u1" }
            assert frames(alice, 1)[0]["event"] == "member_left"

            alice.send_json({ "event": "subscribe", "channel": "private-staff" })

            assert frames(alice, 1)[0]["event"] == "subscribed"

            told = client.post("/announce", json={ "title": "Launch" }).json()

            assert told["data"]["listeners"] == 0
            relayed = frames(alice, 2)

            assert [frame["channel"] for frame in relayed] == ["news", "private-staff"]
            assert relayed[0] == { "event": "Announced", "channel": "news", "data": { "title": "Launch" } }

            alice.send_json({ "event": "ping", "id": "p1" })
            alice.send_json({ "event": "dance" })
            alice.send_text("not json")

            assert [frame["event"] for frame in frames(alice, 3)] == ["pong", "error", "error"]
            assert hub.stats()["connections"] == 3 and hub.stats()["published"] >= 6

            with pytest.raises(WebSocketDisconnect) as full, client.websocket_connect("/ws?token=alice") as fourth:
                fourth.receive_json(mode="binary")

            assert full.value.code == 1013

        assert hub.stats()["connections"] == 0 and hub.channels() == {}

    def test_oversized_frames_close_the_socket_and_slow_consumers_are_shed ( self ) -> None:

        hub, _, app = wire()

        with TestClient(app) as client, client.websocket_connect("/ws?token=alice") as alice:

            frames(alice, 1)
            alice.send_text("x" * 300)

            with pytest.raises(WebSocketDisconnect) as big: alice.receive_json(mode="binary")

            assert big.value.code == 1009

        async def shed () -> tuple[int, int, bool]:

            stub = StubSocket()
            slow = hub.attach(Connection("slow", stub, outbox=asyncio.Queue(2)))

            hub.join(slow, "flood")

            for index in range(5): hub.publish("flood", "drip", index)

            await asyncio.sleep(0)

            return slow.dropped, hub.stats()["dropped"], slow.closed

        dropped, shed_total, closed = asyncio.run(shed())

        assert dropped == 3 and shed_total == 3 and closed is True
        assert Frame.decode(Frame("x", "c", { "k": 1 }, "7").encode()) == Frame("x", "c", { "k": 1 }, "7")

        with pytest.raises(Fault): Frame.decode('{"event": ""}')
        with pytest.raises(Fault): Frame.decode("[1]")
