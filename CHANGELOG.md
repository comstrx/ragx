# Changelog

Every release of RagX, one section per tag, one block per part.

## Unreleased

### api

- The whole part moves under `src/` (`core app config routes bootstrap database views storage`), with `tests/` and `benches/` beside it.
- `core/database` rebuilt on SQLAlchemy Core (asyncpg driver) behind an `Adapter` (PostgreSQL today): a migration DSL with no SQL in migration files (`id uuid string text integer boolean json decimal enum foreign morphs timestamps soft_deletes index unique`, alter/rename/drop), a batch migrator with rollback, and a generative `Query[M]` ORM over frozen dataclass models with `belongs_to has_one has_many belongs_to_many morph_many morph_to`, soft-delete scopes, pagination and typed faults; uuid7 primary keys by default.
- New domains: `crypto` (argon2id, Fernet with rotation, digests, HMAC), `token` (JWT adapter, claims, bearer parsing), `mail` (SMTP/log/memory transports, a mailable DSL), `view` (Jinja, async), `validate` (pydantic adapters cached per type), `value`, `rand`, `func`, `cache` (with a sliding rate counter), `net`, `fs`.
- Route DSL: `Route.get/post/…`, `.guarded(*deps)`, `.limited("60/minute")`, `.constrained(key="int")`, `Route.group(prefix, routes, tags, middleware, throttle, name)`, `Route.resource(prefix, controller)`; throttle answers `429` with `X-RateLimit-*` headers.
- Auth lifecycle: `POST /v1/auth/register|login|refresh|logout`, `GET /v1/auth/me`; argon2id passwords hashed off the event loop, stateless access tokens, hashed and rotated refresh tokens in a `tokens` table (morph owner), roles through `role_user`, a welcome mail rendered from `views/mail/`.
- Reads and single-statement writes run on autocommit connections from one warm pool; string filters bind untyped so PostgreSQL infers enum, uuid and text columns.
- Tests: brutal flat files (laws, core, database, http, auth, storage, pipeline, realtime) against the real `ragx_test` database; flat benches (hello, auth, micro, socket) that fail on any non-200 or a blown p99 budget.
- `core/config`: `env` loads `.env` then `.env.<mode>` (`local`, `testing`, `production`/`prod`) then `.secret` layers with the process environment on top; `config.register/get/set/remove` over typed settings per domain (`app auth broadcast database docs log mail queue schedule socket storage`).
- `core/json` (orjson behind one facade) used by fs, value, net, http and the socket frames; unified types from core (`DateTime TimeDelta Uuid Path Decimal JsonValue`) with a law that no layer above core imports the standard library for them.
- `core/exceptions` replaces `core/error`: one `Handler` maps any exception to a typed `Fault`, reports 5xx with the cause, and `app/exceptions` declares the app mappings and the auth exceptions; nothing escapes as a raw server error.
- `core/storage`: `LocalDisk` and `S3Disk` (obstore) behind one DSL with public/private disks, dated folders (`{Y}/{m}/{d}`, any pattern), a validated upload verb and streamed private downloads; the bootstrap serves `storage/app/public` under `STORAGE_URL`.
- `core/queue` (memory and sync drivers, retries with backoff, burial hook, `queue.task` for any function), `core/event` (dispatch, queued or inline listeners by inheritance, wait-for), `core/schedule` (cron matcher, intervals, timezones, overlap guard); `app/jobs`, `app/events`, `app/listeners`, queued mails; maps in `routes/events` and `routes/schedule`; `python -m bootstrap work|schedule`.
- `core/socket` (WebSocket hub: per-connection bounded outboxes, pings, frame limits, presence, slow-consumer shedding) and `core/broadcast` (channel DSL with public/private/presence authorization, event relay, local driver) declared in `routes/channel` and mounted at `SOCKET_PATH`.
- Docs are configuration: `config/docs.py` drives the Scalar page, the OpenAPI path, theme, tag order, hidden tags and the error envelope responses injected into every operation.
- `app/support` → `app/utils`, `app/Mail` → `app/mails`; `APP_PREFIX` moves the version prefix into `bootstrap/app.py` routing.
- `core/assets` and `src/public`: project assets (brand images, `robots.txt`, future SEO files) served under `ASSETS_URL` with `Cache-Control: public, max-age, immutable`, content-stamped urls (`?v=<sha>`), absolute urls when `APP_URL` is set, a confined path resolver that refuses traversal and dotfiles, and the `assets()` global in every view; `/robots.txt` is a route.
- `core/queue` gains a RabbitMQ driver (direct exchange, quorum queues, a `.wait` queue with dead-lettering for delays, receipts acknowledged after perform, retry or burial); `core/event` becomes an adapter over a `Bus`: `LocalBus` delivers in process, `RabbitBus` publishes every event to a topic exchange and a consumer task delivers to the listeners of every process; `core/cache` gains a Redis store; `config/queue`, `config/event` and `config/cache` choose the drivers (`memory|sync|rabbitmq`, `local|rabbitmq`, `memory|redis`) and their urls, exchanges, prefetch and prefixes.
- `python -m bootstrap runbook` masks the credentials inside every url it prints.
- Confirmation lap: `STORAGE_ROOT/PUBLIC/PRIVATE/LOGS` place the disks and the log folder anywhere (relative to the api root or absolute, `../storage` or `/var/www/storage` with nothing else to configure), `LOG_FILE` writes JSON lines there, uploads refuse `STORAGE_BLOCKED` extensions, every answer carries `X-Content-Type-Options: nosniff`, sockets accept text and binary frames, `Query` gains `first_or_create update_or_create increment decrement chunk`, and the core tests now pin the env layers, the config DSL, json and the exception handler; `python -m bootstrap runbook` prints the operational facts with secrets redacted.

### web

- `SPEC_API_URL` at build time replaces a spec's production and browser api urls and closes its cleartext allowance when the origin is https; the deployment decides the api origin, the spec keeps its lab values.
- Indexing is behavior, not a setting: `settings.seo` is gone; a screen is indexed when it renders on the server, is open to everyone and is not `index: false`, the spec is crawlable when such a screen exists and `contents.url` is set, and the validator refuses `index: true` on a client-rendered or gated screen, robots rules without an indexable screen, and an indexed screen without a site url. The compiled schema carries `indexed` (a count) and the build meta reports it.

### global

- The infra workflow builds the api image and one web image on every infra, lockfile or manifest change; Dependabot drops the helm and opentofu ecosystems; the trivy exception file is empty again.

### infra

- The platform is a Docker Compose monolith on any Linux box; OpenTofu, Kubernetes, Argo CD, Helm and the AWS modules are gone, the bundle (`src/{core,forge,module,template}` → one file) stays.
- `compose` renders the stack from `.env.example` knobs and the manifest: nginx 1.29 unprivileged (TLS 1.2/1.3, HTTP/2, HTTP/3, `X25519MLKEM768` first, HSTS preload, `ssl_reject_handshake` for unknown names, per-client `limit_req` buckets for the api, auth and web, an edge cache for assets and public files, websocket upgrade on `/ws`, lazy upstream resolution so a rolling api never breaks the edge), the api with `worker` and `scheduler` profiles, one image per web spec behind the `web` profile, PostgreSQL 18 (tuned from `PG_MEMORY_MB`, scram only, the superuser never over the network, the app role `NOBYPASSRLS`, `pg_stat_statements` in the maintenance database), RabbitMQ 4.2 (quorum by default, loopback users off) and Redis 8 (ACL from the container env, default user off, `allkeys-lru`) on an internal network, a backup sidecar and certbot behind the `ops` profile; every container drops capabilities, forbids privilege escalation and runs on a read-only root.
- `server deploy` prepares the box (docker, compose, sysctl), logs into the registry, converges the Cloudflare names and the certificate when a token exists, deploys, installs systemd units (stack on boot, nightly backup timer, renewal timer) and verifies the release on the box; `ci release` builds the api, its backup sidecar and the web images, proves them, pushes, scans, converges the server and waits for the edge to serve the tag.
- `compose roll` starts the new container beside the old and retires the old only when the new is healthy (verified: zero failed requests during a roll); `compose rollback` redeploys the previous recorded release; `backup now|list|fetch|restore` dump with `pg_dump -Fc -Z zstd` into a volume or S3 and restore only into a side database; `edge issue|renew|reload|test`; `pg shell|activity|size|slow|tune`; `audit edge|tls|services|backup|all|watch`; `app run|migrate|status|runbook|shell` act locally on the box and travel over ssh from anywhere else.
- Secrets never touch the disk as world-readable files: env files are `0600`, the Redis ACL is declared from the container's own env, the Cloudflare token reaches certbot as a compose secret from the environment, and a quote or a placeholder in a secret is refused before anything renders.
- The web image builds any spec with `bun` and `node 26`, bundles the release server into one file and ships only the build output (no `node_modules`; a standalone site is pre-staged and writes its cache on a tmpfs); the api image gains fast start-up health probing.

## v0.1.0 — 2026-10-17

### api

- A generic `core/` engine: `http` (routes, envelope, trace, handler, warm, lifespan), `database` (asyncpg pool, safe query builder, migrator, seeders, row mapping, error translation), `log` (structlog with spans), `error` (one typed fault and one code set), `config`, `context`, `thread`, `date`, `string`, `array`, `number`.
- One lifecycle through every layer: `GET /v1/hello` → controller → service → repository → `User` model → `users` table, with enums, dna (identity, timestamps, soft deletes) and the base classes.
- A parallel bootstrap that opens the pool, applies migrations, warms the OpenAPI schema and the hot routes, and reports its timings; `python -m bootstrap serve | migrate | seed | check`.
- `/health` reports the database pool and degrades to `503 unavailable` when it is gone.

### infra

- OpenTofu → Kubernetes → Argo CD → Helm stacks (`standard`, `light`, `full`) with the api wired to the same `DB_*` variables the api reads.

### web

- One Next.js engine for every surface: each spec chooses `output` (`export` or `standalone`), `seo` and `render`.
- SEO when a spec asks for it: metadata, canonical and language links, Open Graph and Twitter cards, `robots.txt`, `sitemap.xml`, `manifest.webmanifest` and JSON-LD, all derived from the spec and refused at compile time when they contradict it.
- Three specs saying hello: `super` and `admin` as client-only static exports, `client` as a server-rendered indexable site; one element, one component and one feature carry the greeting.
- A release server for exports with security headers, a Content Security Policy, brotli/gzip and weak validators, and a launcher for standalone builds.
