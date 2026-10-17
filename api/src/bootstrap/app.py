from core.assets import assets
from core.broadcast import broadcast
from core.cache import RedisStore, cache
from core.config import config, env
from core.crypto import crypto
from core.database import database
from core.event import Bus, LocalBus, RabbitBus, events
from core.exceptions import exceptions
from core.fs import Path
from core.http import App, Group, Response, Route, Served, http
from core.log import log
from core.mail import LogTransport, MemoryTransport, SmtpTransport, Transport, mail
from core.queue import Driver as QueueDriver, MemoryDriver, RabbitDriver, SyncDriver, queue
from core.rand import rand
from core.socket import Limits, socket
from core.storage import Disk, LocalDisk, S3Disk, S3Options, storage
from core.token import JwtAdapter, token
from core.view import view
from config import (
    AppConfig, AssetsConfig, AuthConfig, BroadcastConfig, CacheConfig, DatabaseConfig, DocsConfig, EventConfig,
    LogConfig, MailConfig, QueueConfig, ScheduleConfig, SocketConfig, StorageConfig,
)
from app import services
from app.exceptions import ExceptionHandler
from routes import api, channel as channels, events as subscriptions, schedule as timetable
from .boot import Boot

class Application:

    root   = Path(__file__).resolve().parents[2]
    source = Path(__file__).resolve().parents[1]

    def __init__ ( self ) -> None:

        env.load(self.root)

    def settings ( self ) -> AppConfig:
        return config.register("app", AppConfig)

    def logging ( self ) -> LogConfig:
        return config.register("log", LogConfig)

    def database ( self ) -> DatabaseConfig:
        return config.register("database", DatabaseConfig)

    def auth ( self ) -> AuthConfig:
        return config.register("auth", AuthConfig)

    def mailing ( self ) -> MailConfig:
        return config.register("mail", MailConfig)

    def docs ( self ) -> DocsConfig:
        return config.register("docs", DocsConfig)

    def files ( self ) -> StorageConfig:
        return config.register("storage", StorageConfig)

    def queues_config ( self ) -> QueueConfig:
        return config.register("queue", QueueConfig)

    def scheduling ( self ) -> ScheduleConfig:
        return config.register("schedule", ScheduleConfig)

    def realtime ( self ) -> SocketConfig:
        return config.register("socket", SocketConfig)

    def broadcasting ( self ) -> BroadcastConfig:
        return config.register("broadcast", BroadcastConfig)

    def statics ( self ) -> AssetsConfig:
        return config.register("assets", AssetsConfig)

    def caching ( self ) -> CacheConfig:
        return config.register("cache", CacheConfig)

    def eventing ( self ) -> EventConfig:
        return config.register("event", EventConfig)

    def boot ( self ) -> Boot:

        settings = self.settings()

        return Boot(
            self.source, database, self.database(), settings.name, self.queues_config(), self.scheduling(),
            paths=("/health", f"{settings.prefix}/hello"),
        )

    def create ( self ) -> App:

        settings = self.settings()
        logging  = self.logging()

        log.setup(logging.level, logging.renderer, self.logfile())

        self.wire(settings)

        facts = { "version": settings.version, "release": settings.release, "env": settings.env }

        app = http.build(
            settings.name, settings.version, [self.routing(settings)], debug=settings.debug, docs=self.docs(),
            facts=facts, origins=settings.origins, lifespan=self.boot().lifespan,
        )

        http.serve(app, self.files().url, self.files().public_path(self.root), name="storage")
        http.serve(app, self.statics().url, self.statics().path(self.root), name="assets", cache=self.statics().cache)
        app.add_api_route("/robots.txt", self.robots, methods=["GET"], include_in_schema=False, name="robots")

        if self.realtime().enabled: app.add_api_websocket_route(self.realtime().path, socket.endpoint, name="socket")

        return app

    async def robots ( self ) -> Served:
        return Response.file(assets.path("robots.txt"), media="text/plain")

    def routing ( self, settings: AppConfig ) -> Group:

        version = settings.prefix.strip("/").replace("/", ".") or None

        return Route.group("", [api.heartbeat, Route.group(settings.prefix, api.routes, name=version)])

    def wire ( self, settings: AppConfig ) -> int:

        auth    = self.auth()
        mailing = self.mailing()
        files   = self.files()
        jobs    = self.queues_config()
        live    = self.realtime()
        statics = self.statics()
        caching = self.caching()
        secret  = auth.secret or self.ephemeral(settings)

        exceptions.use(ExceptionHandler())
        token.setup(JwtAdapter(secret, auth.algorithm, auth.issuer))
        crypto.setup(auth.keys or [crypto.key()])
        assets.setup(statics.path(self.root), statics.url, settings.url, statics.versioned)
        view.setup(self.source / "views", { "app": settings.name, "assets": assets.url })
        mail.setup(self.transport(mailing), mailing.sender, mailing.name)
        storage.setup(self.disks(), files.disk, files.pattern, files.max_size, files.allowed, files.blocked)
        queue.setup(self.driver(jobs), tuple(jobs.queues), jobs.tries, jobs.backoff)
        events.setup(self.bus(settings))
        events.subscribe(subscriptions.listeners)

        if caching.driver == "redis": cache.use(RedisStore(caching.url, caching.prefix))
        services.auth.configure(auth.access_ttl, auth.refresh_ttl)
        socket.setup(Limits(live.connections, live.queue, live.frame, live.ping, live.drops))

        if self.broadcasting().enabled: broadcast.setup(socket, services.auth.bearer)

        return len(timetable.tasks) + len(channels.channels)

    def ephemeral ( self, settings: AppConfig ) -> str:

        missing = "AUTH_SECRET is required in production"

        if settings.env.is_production(): raise RuntimeError(missing)

        log.warning("auth.ephemeral_secret", env=settings.env.value)

        return rand.token(48)

    def logfile ( self ) -> Path | None:

        logging = self.logging()

        return self.files().logs_path(self.root) / logging.file if logging.file else None

    def disks ( self ) -> dict[str, Disk]:

        files = self.files()
        disks: dict[str, Disk] = {
            "public"  : LocalDisk("public", files.public_path(self.root), files.url),
            "private" : LocalDisk("private", files.private_path(self.root)),
        }

        if files.s3_bucket:

            options = S3Options(
                files.s3_region, files.s3_endpoint, files.s3_key, files.s3_secret, files.s3_prefix, files.s3_path_style,
            )

            disks["s3"] = S3Disk("s3", files.s3_bucket, options, files.s3_url or None)

        return disks

    def driver ( self, jobs: QueueConfig ) -> QueueDriver:

        if jobs.driver == "rabbitmq": return RabbitDriver(jobs.url, jobs.exchange, jobs.prefetch)

        return SyncDriver() if jobs.driver == "sync" else MemoryDriver()

    def bus ( self, settings: AppConfig ) -> Bus:

        eventing = self.eventing()

        if eventing.driver != "rabbitmq": return LocalBus()

        inbox = eventing.queue or f"{settings.name.lower()}.events"

        return RabbitBus(eventing.url, eventing.exchange, inbox, eventing.prefetch)

    def transport ( self, mailing: MailConfig ) -> Transport:

        if mailing.driver == "memory": return MemoryTransport()
        if mailing.driver == "log": return LogTransport()

        return SmtpTransport(
            mailing.host, mailing.port, mailing.username, mailing.password,
            tls=mailing.tls, ssl=mailing.ssl, timeout=mailing.timeout, verify=mailing.verify,
        )
