from core.assets import assets
from core.broadcast import (
    Driver as BroadcastDriver, LocalDriver as LocalBroadcast, RedisDriver as RedisBroadcast, broadcast,
)
from core.cache import RedisStore, cache
from core.config import config, env
from core.crypto import crypto
from core.database import database, outbox
from core.event import Bus, LocalBus, RabbitBus, events
from core.error import Code, Fault
from core.exception import exception
from core.fs import Driver, LocalDriver, Path, S3Driver, S3Options
from core.http import App, Group, Response, Route, http
from core.llm import ChatGpt, Claude, DeepSeek, Gemini, Local, llm
from core.log import log
from core.mail import LogMailer, Mailer, Mailgun, mail
from core.queue import Driver as QueueDriver, MemoryDriver, RabbitDriver, SyncDriver, queue
from core.rand import rand
from core.socket import Limits, socket
from core.storage import storage
from core.token import JwtAdapter, token
from core.view import view
from config import (
    AppConfig, AuthConfig, BroadcastConfig, CacheConfig, DatabaseConfig, DocsConfig, EventConfig, LogConfig, MailConfig,
    QueueConfig, StorageConfig,
)
from app import services
from app.enums import Table
from app.exceptions import ExceptionHandler
from app.utils.dna import passwords
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

    def broadcasting ( self ) -> BroadcastConfig:

        return config.register("broadcast", BroadcastConfig)

    def caching ( self ) -> CacheConfig:

        return config.register("cache", CacheConfig)

    def eventing ( self ) -> EventConfig:

        return config.register("event", EventConfig)

    def boot ( self ) -> Boot:

        settings = self.settings()

        return Boot(
            self.source, database, self.database(), settings.name, self.queues_config(),
            paths=("/health", f"{settings.prefix}/hello"), primers=(passwords.decoy,),
        )

    def create ( self ) -> App:

        settings = self.settings()
        logging  = self.logging()

        log.setup(logging.level, logging.renderer, self.logfile())

        self.wire(settings)

        facts = { "version": settings.version, "release": settings.release, "env": settings.env }

        app = http.build(
            settings.name, settings.version, [self.routing(settings)], debug=settings.debug, docs=self.docs(),
            facts=facts, origins=settings.origins, lifespan=self.boot().lifespan, proxies=settings.proxies,
        )

        app.serve(self.files().url, self.files().public_path(self.root), name="storage")
        files = self.files()
        live  = self.broadcasting()

        app.serve(files.assets_url, files.assets_path(self.root), name="assets", cache=files.assets_cache)
        app.route(Route.get("/robots.txt", self.robots, name="robots").hide())

        if live.socket: app.socket(live.path, socket.endpoint, name="socket")

        return app

    async def robots ( self ) -> Response:

        return Response.file(assets.path("robots.txt"), media="text/plain")

    def routing ( self, settings: AppConfig ) -> Group:

        version = settings.prefix.strip("/").replace("/", ".") or None

        return Route.group("", [api.heartbeat, Route.group(settings.prefix, api.routes, name=version)])

    def wire ( self, settings: AppConfig ) -> int:

        auth    = self.auth()
        mailing = self.mailing()
        files   = self.files()
        jobs    = self.queues_config()
        live    = self.broadcasting()
        caching = self.caching()
        secret  = auth.secret or self.ephemeral(settings)

        exception.use(ExceptionHandler())
        token.setup(JwtAdapter(secret, auth.algorithm, auth.issuer))
        crypto.setup(auth.keys or [crypto.key()])
        assets.setup(files.assets_path(self.root), files.assets_url, settings.url, files.versioned)
        view.setup(self.source / "views", { "app": settings.name, "assets": assets.url })
        mail.setup(mailing.sender, mailing.name, self.mailer(mailing))
        storage.setup(self.disks(), files.disk, files.pattern, files.max_size, files.allowed, files.blocked)
        queue.setup(self.driver(jobs), tuple(jobs.queues), jobs.tries, jobs.backoff)
        events.setup(self.bus(settings))
        outbox.setup(Table.OUTBOX)
        queue.durable(outbox)
        events.durable(outbox)
        events.subscribe(subscriptions.listeners)

        if caching.driver == "redis": cache.use(RedisStore(caching.url, caching.prefix))
        services.auth.configure(auth.access_ttl, auth.refresh_ttl)
        socket.setup(Limits(live.connections, live.outbox, live.frame, live.ping, live.drops))

        if live.enabled: broadcast.setup(socket, services.auth.bearer, self.broadcaster())
        if live.enabled: broadcast.durable(outbox)

        self.models()

        return len(timetable.tasks) + len(channels.channels)

    def broadcaster ( self ) -> BroadcastDriver:

        live = self.broadcasting()

        return RedisBroadcast(socket, live.url, live.topic) if live.driver == "redis" else LocalBroadcast(socket)

    def models ( self ) -> int:

        wait, retries = env.float("LLM_TIMEOUT", 60.0), env.int("LLM_RETRIES", 1)
        keys          = { name: env.text(f"LLM_{name}_KEY") for name in ("OPENAI", "ANTHROPIC", "GEMINI", "DEEPSEEK") }

        llm.setup(env.text("LLM_DRIVER", "local"), env.float("LLM_SESSION_TTL", 3600.0))
        llm.register(Local(env.get("LLM_LOCAL_URL"), env.get("LLM_LOCAL_MODEL"), env.get("LLM_LOCAL_KEY"), wait))

        if keys["OPENAI"]: llm.register(ChatGpt(keys["OPENAI"], *self.llm("OPENAI"), wait, retries))
        if keys["ANTHROPIC"]: llm.register(Claude(keys["ANTHROPIC"], *self.llm("ANTHROPIC"), wait, retries))
        if keys["GEMINI"]: llm.register(Gemini(keys["GEMINI"], *self.llm("GEMINI"), wait, retries))
        if keys["DEEPSEEK"]: llm.register(DeepSeek(keys["DEEPSEEK"], *self.llm("DEEPSEEK"), wait, retries))

        return len(llm.names())

    def llm ( self, name: str ) -> tuple[str | None, str | None]:

        return env.get(f"LLM_{name}_MODEL"), env.get(f"LLM_{name}_URL")

    def ephemeral ( self, settings: AppConfig ) -> str:

        missing = "AUTH_SECRET is required in production"

        if settings.env.is_production(): raise Fault(Code.INTERNAL, missing, "auth.secret")

        log.warning("auth.ephemeral_secret", env=settings.env.value)

        return rand.token(48)

    def logfile ( self ) -> Path | None:

        logging = self.logging()

        return self.files().logs_path(self.root) / logging.file if logging.file else None

    def disks ( self ) -> dict[str, Driver]:

        files = self.files()
        disks: dict[str, Driver] = {
            "public"  : LocalDriver(files.public_path(self.root), files.url),
            "private" : LocalDriver(files.private_path(self.root)),
        }

        if files.s3_bucket:

            options = S3Options(
                files.s3_region, files.s3_endpoint, files.s3_key, files.s3_secret, files.s3_prefix, files.s3_path_style,
            )

            disks["s3"] = S3Driver(files.s3_bucket, options, files.s3_url or None)

        return disks

    def driver ( self, jobs: QueueConfig ) -> QueueDriver:

        if jobs.driver == "rabbitmq": return RabbitDriver(jobs.url, jobs.exchange, jobs.prefetch)

        return SyncDriver() if jobs.driver == "sync" else MemoryDriver()

    def bus ( self, settings: AppConfig ) -> Bus:

        eventing = self.eventing()

        if eventing.driver != "rabbitmq": return LocalBus()

        inbox = eventing.queue or f"{settings.name.lower()}.events"

        return RabbitBus(eventing.url, eventing.exchange, inbox, eventing.prefetch)

    def mailer ( self, mailing: MailConfig ) -> Mailer:

        if mailing.driver != "mailgun": return LogMailer()

        return Mailgun(mailing.mailgun_key, mailing.mailgun_domain, mailing.mailgun_region, wait=mailing.timeout)
