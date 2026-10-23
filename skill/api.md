# API

`product/api` is the RagX backend: a Laravel-shaped application over `engine/python`, flat at the part root. The engine is the framework; the application is declarations composed from engine verbs, configured in `config/` and wired only through `bootstrap/`. Today the layers are lawful empty facades serving `/health`, the docs and the assets; the business arrives by vision phases. Gate: `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run python -m bootstrap check`.

## Layout

```
product/api/
├── app/         enums  utils/{dna,cycle}  models  repositories  services  controllers  middlewares  requests  resources
│                mails  jobs  events  listeners  exceptions            (plural lowercase packages)
├── bootstrap/   app.py (Application, the factory)  boot.py (lifespan)  cli.py (commands over engine.cli)  serve.py  __main__.py
├── config/      one engine Settings per group: app auth broadcast(+socket) cache database docs event llm log mail queue(+schedule) storage(+assets)
├── database/    migrations/NNNN_name.py (schema DSL only; 0001_create_outbox)  seeders/
├── routes/      api/ (product routes, prefix added by bootstrap)  channel/  events/ (listener map)  schedule/
├── views/       layouts/ mail/ (Jinja, async)
├── public/      robots.txt, images/brand/… (served under ASSETS_URL with content stamps)
├── storage/     app/{public,private} logs (public under STORAGE_URL; relocatable by STORAGE_*)
├── tests/       test_laws.py  test_application.py  test_cycle.py, then the product's tests
├── benches/     bench_<name>.py on engine.test.Bench, building the real application
├── conftest.py  test env (ragx_test), the session app over the real lifespan, test.client, the mail outbox
└── pyproject.toml  dependencies = ["engine"] by path; ruff ALL, mypy strict, pytest pythonpath = .
```

## Layers and laws

```
engine → app/enums → config → app/utils/dna → app/utils/cycle → models → repositories → services
       → controllers · middlewares · mails · jobs · events · listeners · exceptions → requests · resources → routes
```

glued by `bootstrap/`; `database/` is data the engine runs; `views/` are templates it renders.

- **Import law** (test): `config app database routes` import only `engine` and `app`; `bootstrap` imports everything but `tests`; `tests` and `benches` import the engine, the layers and `pytest` only; above the engine nothing imports a third-party library or a stdlib module beyond `collections typing enum dataclasses contextlib`.
- **Typing law** (test): no layer imports `datetime uuid pathlib decimal json orjson asyncio os re hashlib base64 secrets random time`; the unified types and verbs come from the engine. A leaf that needs a regex, hash or clock asks the engine for a verb.
- **Migration law** (test): numbered files, async `up`/`down`, schema DSL only: no SQL string, no raw call; every index named and `IF NOT EXISTS`, partial uniques for soft-deleted identities, an index on every foreign key, `isolated()` on every tenant table.
- **Isolation law**: importing `bootstrap` has no side effect (`application` is a factory), so the test env wins over `.env`; the shared fixture refuses a non-test database; `bootstrap check` boots twice and fails on any registry or task that grew.
- **Gravity**: a controller is one or two lines over a service (`return self.ok(await self._service.show(key, user))`); a service is a pipeline over repositories and engine verbs; a repository is one `Query` chain per function; a model is a frozen dataclass with relations and tiny predicates; enums carry vocabulary and behavior; mails, jobs, listeners and events are declarations over the cycle bases (`Controller Service Repository Resource Job Event Listener Mail`, no `Base` prefix); requests are `validate.Shape`; inheriting `Queued` queues. When a layer needs more, the more is an engine verb.

## Bootstrap

- `Application()` loads the env layers (`.env`, `.env.<mode>`, `.secret*`, the process wins) and registers configs on demand; `create()` = log setup → wire (exception handler, token, crypto, assets, view, mail, storage disks, cache, queue, events and their outbox, socket limits, broadcasting, llm models by task, the engine heartbeat) → `http.build` with routing, docs and the lifespan → served storage, assets, `/robots.txt`, the socket.
- `Boot.lifespan`: connect, guard against a role that bypasses RLS, migrate and seed when enabled, fill the pool ‖ warm the OpenAPI ‖ primers → warm `/health` → queue workers → events → broadcast → schedule; shutdown in reverse without idle waits.
- `python -m bootstrap [serve | check | runbook | work | schedule | provision | migrate | rollback [steps] [--force] | status | seed]`: `work` runs workers and the event consumer, `schedule` the scheduler, `provision` runs `Cluster.provision` as the admin (`DB_ADMIN_*`), `rollback` in production needs `--force`, `runbook` prints routes, channels, schedule, queues, handlers, commands and the redacted config as JSON.

## Configuration

One `Settings` class per group, `field(default, env=…, ge=…)`, `hidden` names kept out of `describe()`; folded groups keep their env names (`SOCKET_*` in broadcast, `SCHEDULE_*` in queue, `ASSETS_*` in storage). Drivers are keys: `QUEUE_DRIVER memory|sync|rabbitmq`, `EVENT_DRIVER local|rabbitmq`, `CACHE_DRIVER memory|redis`, `MAIL_DRIVER log|mailgun`, `STORAGE_DISK public|s3`, `BROADCAST_DRIVER local|redis`; `APP_PROXIES` lists trusted proxies. `llm` holds one endpoint per model (`LLM_<MODEL>__URL|KEY|MODEL|TASKS…`, tasks routed by `LLM_TASKS__<TASK>`). A new knob is a field with a default, a line in `.env.example`, its wiring and a test when it changes behavior.

## Wire

- Every answer: `data message errors code reason meta.request_id` (+ `page limit total pages`); headers `X-Request-Id`, `X-RateLimit-*`, `Retry-After`, `nosniff`; `Authorization: Bearer`.
- `GET /health`: status, version, release, database pool, checks (database, cache, queue, events, storage, llm), ms; `503` without the pool.
- Socket frames `{event, channel?, data?, id?}` with `connected subscribed unsubscribed member_joined member_left pong error`.
- Throttling keys on `Request.ip()`: `X-Forwarded-For` counts only through `APP_PROXIES`, so spoofed hops stay in the caller's bucket; a `429` carries `Retry-After` and `throttle`. The api must be reachable only from the edge, and production narrows `APP_PROXIES` to it.

## Production contract

The infra mounts the app env read-only at `/app/.env` and forces only what it owns (`APP_HOST APP_PORT`, `DB_MIGRATE=false`, the storage root on its volume, the role variables, `APP_RELEASE=<tag>`). Application policy (`APP_ENV`, debug, docs) belongs to the app env and the app enforces it. The image installs the engine as wheels, runs as uid 10001 on a read-only root with `/tmp` on tmpfs and `storage/` on a volume; `python -m bootstrap` is the entry. Local models are infra services reached only through `LLM_<MODEL>__URL|MODEL|KEY`.

## Tests and benches

- Written on `engine.test`; real `ragx_test` through the real bootstrap lifespan (`APP_ENV=testing MAIL_DRIVER=log QUEUE_DRIVER=memory QUEUE_WORKERS=0 SCHEDULE_ENABLED=false DB_MIGRATE=true DB_SEED=true`); exact values and the failure path (`422` with the field, `401` with the code, a `429` after the limit, a cross-tenant read refused); every fix mutation-checked.
- `benches/bench_boot.py` measures the product: create, ready and shutdown over 8 cycles and the first burst on `/health`; run with `DB_DATABASE=ragx_test`.

## How to add

- **A feature**: enum → migration → model → repository → service → controller → request/resource → route → test in `tests/` → bench when hot.
- **A job, event, listener, mail or task**: a class over its base, declared in `routes/{events,schedule}` or dispatched from a service; a test drains the memory queue.
- **An engine capability**: never here; it is added to `engine/python` with its test, then consumed in one line.

## Traps

- `conftest.py` pins `ragx_test` before anything loads `.env`; benches boot from `.env`, so pass the test database.
- A service module named like a repository singleton shadows it; a model field named `key` collides with `Model.key()`.
