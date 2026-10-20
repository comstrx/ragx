from dataclasses import dataclass
from typing import ClassVar

from core.database import Blueprint, Model, Query, Schema, database
from core.http import Response, Route
from core.rand import Uuid, rand
from core.validate import Shape, field
from benches import Bench
import asyncio

@dataclass(frozen=True, slots=True, kw_only=True)
class Person(Model):

    table      : ClassVar[str] = f"scratch_bench_people_{rand.hex(3)}"
    soft       : ClassVar[bool] = False
    timestamps : ClassVar[bool] = False

    id    : Uuid
    name  : str
    email : str

class Greeting(Shape):

    name : str = field("World", min_length=1, max_length=32, pattern=r"^[\w .'-]+$")

async def hello ( query: Greeting ) -> Response:

    found = await Query(Person, database).where("name", query.name).first()
    shown = { "id": str(found.id), "name": found.name, "email": found.email } if found else None

    return Response.ok({ "message": f"Hello {query.name}", "user": shown })

def define ( table: Blueprint ) -> None:

    table.id()
    table.string("name", 120).index()
    table.string("email", 254)

class HelloBench(Bench):

    rounds      = 3000
    concurrency = 16

    async def run ( self ) -> None:

        async with self.client(Route.get("/v1/hello", hello, name="hello")) as client:

            async with database.transaction() as session: await Schema(session).create(Person.table, define)

            try:

                await Query(Person, database).create({ "name": "World", "email": "world@bench.test" })

                async def greet () -> None:

                    reply = await client.get("/v1/hello", params={ "name": "World" })

                    self.expect("hello", reply.code, 200, reply.text())

                async def health () -> None:

                    reply = await client.get("/health")

                    self.expect("health", reply.code, 200, reply.text())

                await greet()

                latencies, elapsed = await self.measure(greet, self.rounds, self.concurrency)

                self.report("hello", latencies, elapsed, 250.0)

                latencies, elapsed = await self.measure(health, self.rounds, self.concurrency)

                self.report("health", latencies, elapsed, 250.0)

            finally:

                async with database.transaction() as session: await Schema(session).drop(Person.table)

if __name__ == "__main__":

    asyncio.run(HelloBench().run())
