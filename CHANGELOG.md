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

### infra

- `AUTH_SECRET` joins the app secret keys and the required release secrets; the image owns `/app/src/storage`.
- The worker and scheduler processes run `python -m bootstrap work` and `python -m bootstrap schedule`; the chart passes the queue, schedule, socket and storage defaults.

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
