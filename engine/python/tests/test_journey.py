from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import override

from engine.broadcast import Broadcast, RedisDriver
from engine.context import context
from engine.database import Blueprint, Outbox, Schema, database
from engine.event import Event, events
from engine.http import App, Packet, Response, Route, http
from engine.json import json
from engine.llm import CORE, EMBED, RANK, Llm, Local, Model
from engine.net import Answer as Wire, Ask, net
from engine.queue import Queue, RabbitDriver
from engine.rag import Answer, Document, PostgresIndex, Rag
from engine.rand import rand
from engine.socket import Connection, Frame, Socket
from engine.string import string
from engine.test import expect, test
from engine.thread import thread
from engine.validate import Shape, Text
import pytest

AMQP    = "amqp://guest:guest@127.0.0.1:5672/"
REDIS   = "redis://127.0.0.1:6379/15"
SLOT    = "scratch_scope"
SETTING = "app.scope"
WORDS   = ("refund", "money", "ship", "warranty")
REPLY   = "Refunds are paid within 14 days [S1]."
JSON    = { "content-type": "application/json" }

@dataclass(frozen=True, slots=True)
class Indexed(Event):

    scope    : str
    document : str

    @override
    def channels ( self ) -> Sequence[str]:

        return (f"scopes.{self.scope}",)

class Question(Shape):

    body : Text

def vector ( text: str ) -> list[float]:

    words = string.terms(text)

    return [*(float(sum(word.startswith(stem) for word in words)) for stem in WORDS), 0.1]

def answer ( asked: Ask ) -> Wire:

    body = json.loads(asked.body)

    if asked.url.endswith("/embeddings"):
        texts = body["input"] if isinstance(body["input"], list) else [body["input"]]
        rows  = [{ "index": at, "embedding": vector(text) } for at, text in enumerate(texts)]
        return 200, json.encode({ "data": rows }), JSON
    if asked.url.endswith("/rerank"):
        ranks = [{ "index": at, "relevance_score": 1.0 / (at + 1) } for at in range(len(body["documents"]))]
        return 200, json.encode({ "results": ranks }), JSON

    pieces = [json.dumps({ "choices": [{ "delta": { "content": part } }] }) for part in (REPLY[:9], REPLY[9:])]
    done   = json.dumps({ "choices": [{ "delta": {}, "finish_reason": "stop" }] })
    stream = "".join(f"data: {part}\n\n" for part in (*pieces, done, "[DONE]")).encode()

    return 200, stream, { "content-type": "text/event-stream" }

def library ( table: str ) -> Rag:

    wire   = net.mocked(answer)
    models = Llm()
    roles  = (
        ("writer", "generate", CORE), ("vectors", "embed", frozenset({EMBED})), ("ranker", "rank", frozenset({RANK})),
    )

    for name, task, serves in roles:

        models.register(Local(Model(name, "http://llm/v1", name=name, tasks=frozenset({task}), serves=serves), wire))

    return Rag().setup(PostgresIndex(database, table, 5), models)

@pytest.fixture
async def tables ( app: App ) -> AsyncIterator[tuple[str, Outbox]]:

    passages = f"scratch_journey_{rand.hex(3)}"
    relayed  = f"scratch_outbox_{rand.hex(3)}"

    def isolated ( table: Blueprint ) -> None:

        PostgresIndex.define(5)(table)

        table.isolated("scope", SETTING)

    async with database.transaction() as session:

        if not await Schema(session).extended("vector"): pytest.skip("the pgvector extension is not installed")

        await Schema(session).create(passages, isolated)
        await Schema(session).create(relayed, Outbox.define)

    database.follow(SETTING, SLOT)

    box = Outbox(database, relayed, grace=0.0, backoff=0.01)

    try: yield passages, box
    finally:

        database.follow(SETTING, None)

        await box.stop()

        async with database.transaction() as session: await Schema(session).drop_all(passages, relayed)

class TestJourney:

    async def test_a_scoped_upload_crosses_rabbitmq_indexes_under_rls_and_answers_over_sse (
        self, tables: tuple[str, Outbox],
    ) -> None:

        passages, box = tables
        scope, rival  = f"s-{rand.hex(3)}", f"r-{rand.hex(3)}"
        rag           = library(passages)
        jobs          = Queue()
        rabbit        = RabbitDriver(AMQP, f"unit-{rand.hex(3)}", 4)
        topic         = f"unit-{rand.hex(3)}"
        near, far     = Socket(), Socket()
        live          = Broadcast()
        across        = RedisDriver(far, REDIS, topic)
        reader        = far.attach(Connection("far", test.stub()))

        async def index ( name: str, text: str ) -> None:

            await rag.ingest([Document.text(name, f"{name}.md", text)], str(context.get(SLOT)))
            await events.dispatch(Indexed(str(context.get(SLOT)), name))

        far.join(reader, f"scopes.{scope}")
        live.setup(near, driver=RedisDriver(near, REDIS, topic))
        jobs.setup(rabbit, ("default",))
        jobs.durable(box)
        jobs.register(jobs.name_of(index), index)

        await live.start()
        await across.start()

        try:

            expect(jobs.start(1)).equals(1)

            policy = "Refunds are paid back as money within 14 days."

            with context.bind(**{ SLOT: scope }):
                async with database.transaction(): await jobs.push(index, "refunds", policy)

            async def counted () -> bool:

                with context.bind(**{ SLOT: scope }): return await rag.count(scope) > 0

            expect(await thread.poll(counted, 0.05, 15.0)).true()
            expect(await thread.poll(lambda: reader.outbox.qsize() > 0, 0.05, 10.0)).true()

            frames = [Frame.decode(reader.outbox.get_nowait()) for _ in range(reader.outbox.qsize())]

            expect([(frame.event, frame.data) for frame in frames]).equals(
                [("Indexed", { "scope": scope, "document": "refunds" })],
            )

            with context.bind(**{ SLOT: rival }): expect(await rag.count(scope)).equals(0)

            expect(await rag.count(scope)).equals(0)

            async def ask ( body: Question ) -> Response:

                context.set(SLOT, scope)

                async def packets () -> AsyncIterator[Packet]:

                    async for item in rag.stream(body.body, scope):

                        if isinstance(item, Answer):
                            yield { "event": "done", "data": [passage.document for passage in item.citations] }
                        elif item.text: yield { "event": "delta", "data": item.text }

                return Response.sse(packets())

            small = http.build("Journey", "1.0.0", [Route.group("", [Route.post("/ask", ask)])])

            async with test.client(small, "http://journey") as client:

                streamed = (await client.post("/ask", json={ "body": "How do I get my money back?" })).ok().text()

            expect(streamed).contains("event: delta").contains('event: done\ndata: ["refunds"]')
            expect(context.get(SLOT)).none()

        finally:

            await jobs.stop()
            await live.stop()
            await across.stop()
            await rabbit.clear("default")
            await rabbit.close()
