# API

Python 3.15 + FastAPI on uv, everything under `api/src/`. A generic `core/` engine of 30 domains carries every integration; a Laravel-shaped application sits on it as thin pipelines; `bootstrap/` is the only opinionated glue. Gate: `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run python -m bootstrap check`.

## Layout

```
api/
├── src/
│   ├── core/       30 domains, one folder of flat files each, a facade __init__ with __all__ and a lowercase singleton
│   ├── app/        enums  utils/{dna,bases}  models  repositories  services  controllers  middlewares
│   │               requests  resources  mails  jobs  events  listeners  exceptions      (every folder a plural lowercase package)
│   ├── config/     one pydantic-settings class per domain: app assets auth broadcast cache database docs event log mail queue schedule socket storage
│   ├── routes/     api/ (the heartbeat and the routes without the version prefix)  channel/ (broadcast channels)  events/ (listeners map)  schedule/ (tasks)
│   ├── database/   migrations/NNNN_name.py (the schema DSL, no SQL)  seeders/
│   ├── views/      layouts/ mail/  (Jinja, async)
│   ├── public/     project assets: robots.txt, images/brand/…  (served under ASSETS_URL with content stamps)
│   ├── storage/    app/{public,private}  logs   (public served under STORAGE_URL, private only through routes; relocatable by STORAGE_*)
│   └── bootstrap/  app.py (Application: configs, routing, wiring)  boot.py (the lifespan)  commands.py  serve.py  __main__.py
├── tests/          conftest + flat files: test_{laws,core,database,http,auth,storage,pipeline,realtime}.py
├── benches/        __init__ (the Bench base) + flat bench_{hello,auth,micro,socket}.py
└── pyproject.toml  hatchling, [tool.uv] package = true, ruff ALL, mypy strict, pytest pythonpath = src
```

## Layer chain and laws

```
core → app/enums → config → app/utils/dna → app/utils/bases → models → repositories → services
     → controllers · middlewares · mails · jobs · events · listeners · exceptions → requests · resources → routes
```

glued by `bootstrap/`; `database/` is data the core runs; `views/` are templates the core renders.

- **Import law** (a test): `core` imports only `core`; `config`, `app`, `database` and `routes` import only `core` and `app`; `bootstrap` imports everything; the core domains form a DAG checked by AST.
- **Typing law** (a test): outside `core`, no file imports `datetime uuid pathlib decimal json orjson asyncio os re hashlib base64 secrets random time`. The unified types come from the core: `core.date.DateTime/TimeDelta/UTC`, `core.rand.Uuid`, `core.fs.Path`, `core.number.Decimal`, `core.json.JsonValue`; `collections.abc`, `typing`, `enum` and `dataclasses` stay allowed. A leaf that needs a regex, a hash or a clock asks the core for a verb.
- **Core laws**: final wrapper (every third-party library and every network, file, process access lives in `core`; no third-party type crosses its facade); generic engine (no business logic, product name, model or migration); async-only I/O, pure CPU helpers sync, CPU-heavy work offloaded through `thread.offload`; one domain = one folder of flat files + a facade; unified errors (`Fault`); logs for everything; domains depend downward only; `log` is the floor (it serializes with orjson itself so `json → exceptions → log` has no cycle); no `core/base`.
- **Gravity in practice**: a controller is one or two lines over a service; a service is a thin pipeline over repositories and core verbs; a repository is a `Query` chain; a model is behaviorally empty (frozen dataclass + relations + tiny predicates); enums carry the vocabulary and the behavior on their cases; a mail, a job, a listener and an event are declarations over their base classes. When any of these needs more, the "more" is a new verb in a core domain, with a test in `test_core.py` or `test_database.py`.

## The core domains

| Domain                           | Owns                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config`                         | `env` layers (`.env`, `.env.<mode>`, `.secret*`, process wins) and `config.register/get/set/remove/require/names` over typed settings; `Settings.load()` reads the process environment only; settings are frozen, overrides live in `config`                                                                                                                                                                                                                                                                                                |
| `exceptions`                     | `Code` (13 codes: `ok created accepted bad_request unauthorized forbidden not_found method_not_allowed conflict validation too_many_requests internal unavailable`), `Fault(code, reason, message, errors)`, `Faults`, `Handler` (maps exception types to codes, reports ≥ 500 with cause and traceback, < 500 at debug), the FastAPI handlers; nothing leaks a raw 500                                                                                                                                                                     |
| `log`                            | structlog: `setup(level, renderer, file)`, `bind`, `debug info warning error exception`, `span(event, **fields)` with durations, JSON renderer in production, the request id bound per request                                                                                                                                                                                                                                                                                                                                              |
| `json`                           | orjson behind `dumps encode(pretty sort lenient) pretty loads parse valid looks clone flatten dig fallback`; `JsonValue`                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `http`                           | `App(FastAPI)`, the `Route` DSL, `http.build(title, version, groups, debug, docs, facts, origins, lifespan)`, `http.serve(app, url, folder, name, cache)` (static with `immutable` cache headers), `Docs` (Scalar page, OpenAPI path, theme, tags, the envelope schema on every operation), `Response` (`ok created accepted page fail html file stream`), `Trace` (request id, access log, rate headers, `nosniff`), `Throttle` on `cache.hit`; exports `Request Response Depends Header Query Body File Form Upload Html Streamed Served` |
| `database`                       | SQLAlchemy Core async over an `Adapter` (PostgreSQL today): `Database.connect` (one pool `pool_size = max`, LIFO, autocommit view for reads and single statements, `transaction()` for explicit BEGIN), `Translate` SQLSTATE → `Fault`, `Blueprint`/`Schema` migration DSL, `Migrator` (ledger `schema_migrations`, advisory lock, one transaction per batch, `apply rollback reset status`), `Model` + relation helpers, the generative `Query[M]`, `Rows`, `Seeds`                                                                        |
| `storage`                        | `LocalDisk` (atomic writes, path confinement) and `S3Disk` (obstore, signed temporary urls) behind one DSL: `disk clean dated name mime put put_dated upload get text stream exists size delete copy move list url temporary_url`; uploads refuse blocked extensions and sizes                                                                                                                                                                                                                                                              |
| `assets`                         | project assets under `src/public`: `setup(folder, prefix, base, versioned)`, `clean` (refuses `..` and dotfiles), `path` (confined), `stamp` (content sha, cached), `url(path, absolute)` → `/assets/<path>?v=<stamp>`, `mime read text list`; the Jinja global `assets`                                                                                                                                                                                                                                                                    |
| `queue`                          | `Job`, the `Driver` protocol (`push pull size clear ack close`): `MemoryDriver`, `SyncDriver`, `RabbitDriver` (direct exchange, quorum queues, a `.wait` queue dead-lettering for delays, receipts settled after perform/retry/bury); `Queue.setup register push enqueue task perform start stop drain size clear stats on_failure inline`, retries with backoff, burial after `tries`; `Queued` mixin                                                                                                                                      |
| `event`                          | `Event` base (`kind`, registry, `dump/load/of`, broadcast hooks), `Events.setup(bus) listen subscribe on_any dispatch deliver receive replay until start stop`; the `Bus` protocol: `LocalBus` delivers in process, `RabbitBus` publishes every event to a topic exchange and a consumer task delivers to the listeners of every process; a listener that inherits `Queued` is queued, otherwise inline                                                                                                                                     |
| `schedule`                       | `Cron` (five fields, lists, ranges, steps, aliases), `Task` (`at every every_minute hourly daily daily_at weekly_on monthly_on timezone without_overlapping queued named`), `Schedule.call job tasks due run_due start stop status`                                                                                                                                                                                                                                                                                                         |
| `socket`                         | the WebSocket hub: bounded per-connection outboxes, text and binary frames, `subscribe unsubscribe ping pong publish`, presence channels, ping and silent-close, frame limits (1009), full hub (1013), slow consumers shed (1008), `stats channels subscribers close_all`                                                                                                                                                                                                                                                                   |
| `broadcast`                      | `channel(pattern, authorize)` (one definition serves `private-` and `presence-`), `public`, `grant`, `emit`, `to(...).except_(...).send`, the relay of every dispatched event with `channels()`; `LocalDriver`                                                                                                                                                                                                                                                                                                                              |
| `cache`                          | the `Store` protocol, `MemoryStore`, `RedisStore` (json values, `px` ttl, pipelined `incrby`+`pexpire nx`, scan-based clear), `Cache.use get set forget has remember increment hit(key, limit, window) clear close` (the sliding rate counter behind the throttle)                                                                                                                                                                                                                                                                          |
| `crypto`                         | argon2id passwords, Fernet with key rotation, digests, HMAC, `fingerprint`                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `token`                          | JWT issue/verify/claims/bearer parsing over `crypto`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `mail`                           | `SmtpTransport`, `LogTransport`, `MemoryTransport`, a mailable DSL over `view`                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `view`                           | Jinja, async, `render(name, /, **data)`, globals installed by the bootstrap                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `validate`                       | pydantic adapters cached per type                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `value`                          | typed coercion and formatting of loose input: `string text bool integer float …`                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `rand`                           | uuid7 ids, secure tokens, `Uuid`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `date`                           | `DateTime TimeDelta UTC`, stamps, parsing, arithmetic                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `fs`                             | `Path`, async reads and writes, atomic replace, `within`, `walk`                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `net`                            | the http client (`open(wait, headers, retries) request get post put patch delete close` → `Reply(ok text json)`), url helpers, client address helpers                                                                                                                                                                                                                                                                                                                                                                                       |
| `thread`                         | `gather(limit) timeout retry offload once sleep forever run` over the loop and bounded executors                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `context`                        | request-scoped contextvars; no request state survives a request                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `string` `array` `number` `func` | the verb sets every layer composes instead of writing loops                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

## DSLs

Routes (`routes/api/__init__.py`), wrapped by the bootstrap in `Route.group(APP_PREFIX)` so names compose as `v1.auth.login`:

```python
heartbeat = Route.get("/health", health.index, name="health", tags=("health",))
routes: list[Route | Group] = [
    Route.get("/hello", hello.index, name="hello", tags=("hello",)),
    Route.group("/auth", [
        Route.post("/register", auth.register, name="register").limited("10/minute"),
        Route.post("/logout", auth.logout, name="logout").guarded(authenticate),
    ], tags=("auth",), name="auth"),
    Route.group("/files", [
        Route.get("/{path}", files.show, name="show").constrained(path="path"),
    ], tags=("files",), name="files"),
]
```

Migrations: one table per file, no SQL, every index named and created `IF NOT EXISTS`, partial uniques for soft-deleted identities, an index on every foreign key:

```python
class Migration:

    async def up ( self, schema: Schema ) -> None:

        def define ( table: Blueprint ) -> None:

            table.id()
            table.string("name", 120)
            table.string("email", 254)
            table.string("password", 255).nullable()
            table.timestamps()
            table.soft_deletes()
            table.unique(["lower(email)"], name="users_email_alive", where="deleted_at IS NULL")
            table.index("created_at")

        await schema.create(Table.USERS, define)

    async def down ( self, schema: Schema ) -> None:
        await schema.drop(Table.USERS)
```

Blueprint verbs: `id uuid string text integer big_integer small_integer boolean float decimal json date timestamp timestamps soft_deletes enum foreign morphs index unique gin fulltext primary check drop_column rename_column drop_index drop_unique drop_check drop_primary drop_foreign rename_index`, columns chain `.nullable .default .unique .index .key .references`.

Query, generative and immutable: `where… order_by latest oldest limit offset select with_ with_trashed only_trashed get first first_or_fail find find_or_fail count exists pluck paginate chunk create insert update first_or_create update_or_create increment decrement delete force_delete restore`; string binds untyped so PostgreSQL infers enum, uuid and text; reads on autocommit connections, multi-statement writes in `transaction()`.

The lifecycle of one feature, every layer thin:

```python
class HelloController(BaseController):

    async def index ( self, query: Annotated[HelloRequest, Query()] ) -> Response:
        return self.ok(await self._service.greet(query.name))

class HelloService(BaseService):

    async def greet ( self, name: str ) -> dict[str, object]:

        user = await self._users.find_by_name(name)

        self.log.debug("hello.greeted", name=name, known=user is not None)

        return { "message": Message.HELLO.render(name=user.name if user else name), "user": self._resource.maybe(user) }

class SendWelcomeMail(BaseListener, Queued):

    async def handle ( self, event: UserRegistered ) -> None:

        welcome = WelcomeMail(name=event.name, app=config.get("app.name", "RagX")).to(event.email)

        try: await welcome.send_now()
        except Fault as fault: self.log.warning("welcome.skipped", user=event.user_id, reason=fault.reason)
```

## Envelope and protocol

- Every answer: `data message errors code reason meta.request_id` plus `meta.{page,limit,total,pages}` when paginated; headers `X-Request-Id`, `X-RateLimit-*`, `X-Content-Type-Options: nosniff`; `Authorization: Bearer`.
- `GET /health` reports `status version release database{alive ready driver size idle busy overflow}` and degrades to `503 unavailable` without the pool; `release` is `APP_RELEASE` (the image tag in production).
- Socket frames `{event, channel?, data?, id?}` with system events `connected subscribed unsubscribed member_joined member_left pong error`.
- Throttling keys on the first `X-Forwarded-For` hop; the production edge sets that header from the real peer address, never appends.

## Bootstrap and commands

- `Application()` loads the env and registers configs on demand; `create()` = `log.setup → wire → http.build(routing, docs, lifespan) → http.serve(assets) → http.serve(storage public) → /robots.txt → the websocket route`; `wire()` installs the exception handler, token, crypto, assets, view globals, mail transport, storage disks, the cache store, the queue driver, the event bus and subscriptions, auth ttls, socket limits and the broadcasting guard, each chosen by its `config/*` driver key.
- `Boot.lifespan`: connect → migrate/seed ‖ warm the OpenAPI → warm `/health` and `{prefix}/hello` → `queue.start(workers)` → `events.start()` (remote consumer, only in processes with workers) → `schedule.start(tick)`; shutdown: schedule → sockets → events → queue → cache → database.
- `python -m bootstrap serve | migrate | rollback [n] | status | seed | check | work | schedule | runbook`. `work` runs the queue workers and the event consumer without the scheduler; `schedule` runs the scheduler without workers; `check` boots the full lifespan and exits; `runbook` prints routes, channels, schedule, queues, handlers, the redacted config (secrets excluded, url credentials masked) and the operation count as JSON.

## Configuration

One pydantic-settings class per domain in `config/`, env prefix per class (`APP_ DB_ AUTH_ MAIL_ DOCS_ STORAGE_ ASSETS_ QUEUE_ EVENT_ CACHE_ SCHEDULE_ SOCKET_ BROADCAST_ LOG_`), every key documented in `api/.env.example`. Drivers are keys: `QUEUE_DRIVER=memory|sync|rabbitmq`, `EVENT_DRIVER=local|rabbitmq`, `CACHE_DRIVER=memory|redis`, `MAIL_DRIVER=smtp|log|memory`, `STORAGE_DISK=public|s3`, `BROADCAST_DRIVER=local`. A new knob is a field with a default, a line in `.env.example`, and a test when it changes behavior.

## Tests

- Flat, brutal, few: `tests/test_{laws,core,database,http,auth,storage,pipeline,realtime}.py` against the real `ragx_test` database booted through the real lifespan (`conftest.py` sets `APP_ENV=testing MAIL_DRIVER=memory QUEUE_DRIVER=memory QUEUE_WORKERS=0 SCHEDULE_ENABLED=false DB_MIGRATE=true DB_SEED=true`); realtime through Starlette's test client on a bare app; the broker tests drive the real local RabbitMQ and Redis.
- `test_laws.py` is the constitution: the hand style (one blank line, zero comments, the `__main__` shape), the import direction and the core DAG, migrations speaking only the DSL, every core domain exporting a facade and the root importing every domain. A new domain or layer registers itself there.
- A test asserts exact values and the failure path (`422` with the field, `401` with the code, a `Fault` with the reason, a `429` after the limit, a rejected upload, a tampered token, a cross-tenant read refused). A test that mocks something runnable, or that passes without exercising code, is removed.
- Performance budgets live in the benches, not in the tests.

## Benches

`benches/__init__.py` provides `Bench` (`quiet`, `budget(label, fallback)` from `BENCH_<LABEL>_P99_MS` × `BENCH_SCALE`, `client()` over the real lifespan, `measure(work, rounds, concurrency)` and `measure_sync`, p50/p95/p99 reporting). Each flat `bench_<name>.py` is a law: it prints throughput and percentiles and exits non-zero on any unexpected status or a blown p99. Benches run on demand (`uv run python -m benches.bench_hello`), never in CI; their numbers go into the report and, when durable, into `README.md`.

## Lint and types

- ruff 0.17+, `select = ["ALL"]`, 120 columns, `src = ["src","tests","benches"]`; per-file ignores are listed in `pyproject.toml` with their reason in the commit (complexity in the code set and the enums, `S608` in the query builders and seeders, `BLE001` in the job, schedule and bus runners that must survive a failing job, `T201` in the command entry point and the benches, the test allowances).
- mypy strict with `warn_unreachable` and the pydantic plugin over `src tests benches`. Protocols with properties describe settings so `Literal` fields satisfy `str`; a `Fault` re-raised from itself hides the cause; `FastAPI.openapi` is overridden by subclassing; dataclass fields never shadow a base attribute.

## How to add

- **A core verb or domain**: create the flat file(s) and the facade, register the singleton in `core/__init__.py`, add it to the DAG order, pin it in `test_core.py`, document it in the table above. No product words inside.
- **A lifecycle feature**: enum → migration (DSL) → model → repository → service → controller → request/resource → route → test (`test_http.py` or its own flat file) → bench when hot. Each layer stays one or two lines; the moment a layer needs more, go back to the core.
- **A job, event, listener, mail or task**: a class over its base, declared in `routes/{events,schedule}` or dispatched from a service; `Queued` decides queued vs inline; a test drains the memory queue by hand.
- **A config knob**: a field with a default, `.env.example`, the wiring branch in `bootstrap/app.py`, a test when it changes behavior, the infra template `compose/api.env` when production must set it.
- **A provider** (LLM, mail, storage, broker): a core adapter behind a protocol, chosen by a driver key, with a memory/local implementation for tests and a real one exercised against the real service in `test_pipeline.py`.

## Production contract

The infra renders the api env from its own knobs: `APP_HOST=0.0.0.0 APP_PORT=8000 APP_RELEASE=<tag> APP_URL APP_ORIGINS`, `DB_*` to the `postgres` service, `QUEUE_URL`/`EVENT_URL` to `rabbitmq`, `CACHE_URL` to `redis`, `LOG_RENDERER=json`, `STORAGE_*`, `AUTH_SECRET`, `DOCS_ENABLED`; the http process runs `QUEUE_WORKERS=0` and `SCHEDULE_ENABLED=false` when a worker and a scheduler service exist. The image runs as uid 33 on a read-only root with `/tmp` on tmpfs and `src/storage` on a volume; `python -m bootstrap` is the entrypoint and `serve work schedule migrate status runbook` its verbs. A new environment key the api needs in production is added to `infra/src/template/compose/api.env` in the same change.
