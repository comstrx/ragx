from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from engine.broadcast import broadcast
from engine.cache import cache
from engine.config import env
from engine.crypto import crypto
from engine.database import Adapter, Cluster, Provision, Provisioned, Schema, adapters, database, outbox
from engine.event import LocalBus, events
from engine.exception import Handler, exception
from engine.health import heartbeat
from engine.http import App, Group, Route, http
from engine.llm import llm
from engine.log import log
from engine.mail import LogMailer, mail
from engine.queue import MemoryDriver, queue
from engine.rand import rand
from engine.schedule import schedule
from engine.socket import socket
from engine.token import JwtAdapter, token
import asyncio

QUEUES = ("default", "maintenance")

class Relay:

    def __init__ ( self, host: str, port: int ) -> None:

        self._target = (host, port)
        self._server : asyncio.Server | None = None
        self._links  : list[asyncio.StreamWriter] = []
        self.port    = 0
        self.opened  = 0

    def url ( self, scheme: str, path: str = "", user: str = "" ) -> str:

        return f"{scheme}://{user}{'@' if user else ''}127.0.0.1:{self.port}{path}"

    async def up ( self ) -> int:

        if self._server is None:

            self._server = await asyncio.start_server(self.pipe, "127.0.0.1", self.port)
            self.port    = self._server.sockets[0].getsockname()[1]

        return self.port

    async def pipe ( self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter ) -> None:

        far_reader, far_writer = await asyncio.open_connection(*self._target)

        self.opened += 1

        self._links.extend((writer, far_writer))

        async def pump ( source: asyncio.StreamReader, target: asyncio.StreamWriter ) -> None:

            while chunk := await source.read(65536):

                target.write(chunk)

                await target.drain()

            target.close()

        await asyncio.gather(pump(reader, far_writer), pump(far_reader, writer), return_exceptions=True)

    def sever ( self ) -> int:

        links, self._links = self._links, []

        for link in links: link.transport.abort()

        return len(links) // 2

    async def down ( self ) -> None:

        server, self._server = self._server, None

        self.sever()

        if server is not None:

            server.close()

            await server.wait_closed()

class Stage:

    def application ( self, *routes: Route | Group, name: str = "engine" ) -> App:

        log.setup(env.text("LOG_LEVEL", "warning"))

        self.wire()

        return http.build(name, "0.0.0", [Route.group("", [heartbeat.route(), *routes])], lifespan=self.lifespan)

    def wire ( self ) -> None:

        exception.use(Handler())
        token.setup(JwtAdapter(env.text("AUTH_SECRET", "") or rand.token(48), issuer=env.text("AUTH_ISSUER", "engine")))
        crypto.setup([crypto.key()])
        mail.setup("engine@example.test", "Engine", LogMailer())
        queue.setup(MemoryDriver(), QUEUES)
        events.setup(LocalBus())
        queue.durable(outbox)
        events.durable(outbox)
        heartbeat.register()

    @asynccontextmanager
    async def lifespan ( self, app: App ) -> AsyncGenerator[None]:

        with log.span("stage.boot"): await self.connect()

        try: yield
        finally: await self.stop()

    def adapter ( self ) -> Adapter:

        return adapters.resolve(env.text("DB_DRIVER", "postgresql"))

    def options ( self ) -> dict[str, object]:

        return self.adapter().options(env.text("DB_SSLMODE", "disable"), env.text("DB_SEARCH_PATH", "public"), "engine")

    async def provision ( self ) -> Provisioned:

        plan = Provision(
            host=env.text("DB_HOST", "127.0.0.1"), port=env.int("DB_PORT", 5432),
            admin=env.text("DB_ADMIN_USERNAME", "postgres"), password=env.text("DB_ADMIN_PASSWORD", ""),
            maintenance=env.text("DB_ADMIN_DATABASE", "postgres"), role=env.text("DB_USERNAME", "engine"),
            secret=env.text("DB_PASSWORD", "engine"), database=env.text("DB_DATABASE", "engine_test"),
            extensions=("vector",),
        )

        return await Cluster.provision(self.adapter(), plan, self.options())

    async def connect ( self ) -> None:

        adapter = self.adapter()
        url     = adapter.url(
            env.text("DB_HOST", "127.0.0.1"), env.int("DB_PORT", 5432), env.text("DB_DATABASE", "engine_test"),
            env.text("DB_USERNAME", "engine"), env.text("DB_PASSWORD", "engine"),
        )

        await database.connect(adapter, url, 1, env.int("DB_POOL_MAX", 10), 5.0, self.options())

        async with database.transaction() as session: await Schema(session).create_if_missing("outbox", outbox.define)

        await database.fill(1)

    async def stop ( self ) -> None:

        with log.span("stage.shutdown"):

            await schedule.stop()
            await socket.close_all()
            await broadcast.stop()
            await events.stop()
            await outbox.stop()
            await queue.close()
            await llm.close()
            await cache.close()
            await database.close()
