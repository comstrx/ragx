# Python engine

`engine/python` is the server engine: a uv workspace of 42 domain packages under one namespace, `engine`, and a facade distribution, also named `engine`, that depends on all of them. Every server integration lives here; nothing here knows a product. `product/api` depends on the facade by path; the day the engine leaves for its own repository, that one line becomes a release reference. Goal: Laravel's breadth and ease, FastAPI's speed, total security, the best measured latency in Python. Gate: `uv run ruff check`, `uv run mypy`, `uv run pytest`.

## Layout

```
engine/python/
├── pyproject.toml          the facade `engine` (depends on every engine-<domain>), the workspace (members = ["src/*"]),
│                           one workspace source per member, and every tool config (ruff ALL, mypy strict, pytest)
├── uv.lock                 one lock for the workspace
├── src/<domain>/           one member: pyproject.toml (engine-<domain>: the engine domains and pinned libraries it imports)
│   └── engine/<domain>/    the package: __init__.py facade with __all__ and a lowercase singleton, flat files, py.typed
├── conftest.py             neutral env (engine_test / engine), test.provision(), the session app from test.application()
├── tests/                  flat test_<area>.py on engine.test, real services only
└── benches/                flat bench_<name>.py on engine.test.Bench
```

`engine/` has no `__init__.py` anywhere: it is a PEP 420 namespace shared by the members, so importing `engine.http` loads only the DAG of `http`.

## Laws

- **Final wrapper**: every third-party library and every network, file, process, database, broker and model access lives here; no library type crosses a facade (the one declared raw surface is `engine.database` speaking SQLAlchemy). Hiding a library means owning its semantics, errors and options, never re-exporting aliases.
- **Product-free**: no business rule, product name, tenant, model or migration. A test asks "would this survive deleting every product?".
- **Manifest law** (`tests/test_workspace.py`): the facade depends on exactly every member; each member is named `engine-<dir>`, ships `engine/<dir>/`, carries the facade's version, declares exactly the engine domains it imports and every library it imports, pinned with `==` (runtime drivers `asyncpg`, `python-multipart`, `httpx2` excepted from "imported").
- **Shape law** (`tests/test_laws.py`): a domain is one folder of flat files of 100–300 lines (a smaller module merges into its sibling, a larger one sheds a mixin) plus a facade; every facade has `__all__` and `py.typed`; domains form a DAG with `log` as the floor and `error`/`exception` split so nothing cycles; nothing reaches a product package; the engine raises only `Fault`; facades export only engine or stdlib names; public verbs speak no library type; no verb named like a builtin hides it from its own class; hand style, zero comments; tests and benches import only the engine, `pytest` and their declared proofs.
- **One vocabulary**: `setup ready use register names describe dump load has forget clear stats close`, each stating whether it waits or cancels, whether a retry is safe and what remains (`clear() -> int`, `forget() -> bool`, `stop(wait) -> int`, idempotent), pinned in `tests/test_semantics.py`.
- **One error**: `Fault(code, reason, message, errors)` over 13 codes; a client reason is a fixed code that never echoes input (paths, hosts, values); only `INTERNAL` may name a developer identifier; no traceback or 500 detail reaches a client.
- **One typing**: mypy strict at zero; `DateTime TimeDelta UTC Uuid Path Decimal JsonValue` are defined here for every layer above; async-only I/O, CPU-heavy work through `thread.offload`, nothing blocks the loop.
- **Security law**: input filtered at the boundary (`validate.Shape`, rulebook rules compiled to native constraints), secrets redacted in every log, paths confined, uploads policed, archive bombs bounded, SSRF-safe egress, argon2id passwords, JWT access/refresh pairs with fingerprints, Fernet with key rotation, `X-Forwarded-For` trusted only through configured proxies, tenant isolation by RLS.
- **Adapter law**: every provider is an `engine.adapter.Adapter` with `family`, `name` and declared capabilities; an unsupported capability or option is a `Fault` before any I/O, never a skip or fake success; a missing setting fails at construction (`<family>.<name>.config.<field>`); HTTP providers subclass `engine.net.Remote` (`401/403 → .key`, `429 → .rate` with `retry_after`, `4xx → .request`, else `unavailable`, for calls and SSE alike); registries are `Manager[A]`. Unification never drops a raw capability, performance or security. `gateway` takes one normalized input and returns one dense normalized output (`amount total_amount net_amount gross_amount …`, present even when a provider lacks them) plus `raw`, kept as evidence and never read by logic. A new broker (Kafka, Redpanda) is one more file behind the family.
- **Outbox law**: a side effect that must survive the request (job, remote event, broadcast) is written in the request's transaction (`queue.durable`, `events.durable`, `broadcast.durable`); a rollback erases it, a commit delivers it, a crash delays it to the relay; delivery is at least once, so handlers are idempotent; a deliverer returns only once downstream accepted.
- **Recovery law**: a pooled Postgres connection idle over 5 s is pinged at checkout and replaced when dead; a Redis outage makes `get set lock` raise `UNAVAILABLE cache` while `hit` degrades to a process counter; RabbitMQ rides a robust connection, publishes fail typed while down, consumers resume, a lost ack redelivers; workers supervise `Fault` only. `engine.test.Relay` cuts and restores a real service mid-operation.
- **Tenancy law**: `blueprint.isolated(column, setting)` forces RLS with one fail-closed policy; settings bind per transaction (`database.bound`, or `database.follow(setting, slot)` so a request's jobs and events carry the tenant); binding inside an open transaction is refused; `Cluster.provision` creates the runtime role `NOSUPERUSER NOBYPASSRLS` with its own database and extensions.
- **Egress law**: every user-supplied URL goes through `net.Egress`: public addresses only, the connection pinned to the checked address with the original Host/SNI, each redirect re-checked, no environment proxies.
- **Model law**: the llm layer knows no model name: one `Model` spec builds any driver (`chatgpt claude gemini deepseek local`); work routes by task (`generate summarize evaluate embed rank ocr describe transcribe`), boot refuses a model that cannot serve its task; one tuning vocabulary (a missing feature is a `Fault`, a missing knob is dropped and logged); native structured output only where declared, the full schema always validated locally.
- **Turn law**: a turn is saved only after a validated success, inside a per-session lane with compare-and-set; a stream yields provisional chunks under shrinking deadlines and one `done` after persistence; an incomplete stream or timeout is unknown and saves nothing.
- **Extraction law**: files are read by code first, by a model only where code cannot: a sandboxed `python -I` worker per file under rlimits; Arabic legibility gate for PDFs (pdfium, then pypdf, else an `ocr` gap); what code cannot read returns typed gaps (`ocr vision speech frames`), never invented text.
- **Retrieval law**: a scope is an application namespace, never an authorization; one embedding identity per scope; documents replaced whole after all embeddings exist; sources are untrusted data with control markers stripped; citations name supplied sources.
- **Stage law**: `engine.test` carries the engine's reference application (`test.application(*routes)`: handler, ephemeral key, log mailer, memory queue and local bus over the durable outbox, heartbeat at `/health`, database from `DB_*`) and `test.provision()`, so tests and benches need no product. `Bench` (`engine.test`) measures over it; a product overrides `build` and `prepare`.

## Domains

| Layer     | Domains (what each owns)                                                                                                                                                                                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| floor     | `log` structured logs, spans, redaction · `error` Fault and codes · `context` request id and slots · `exception` the handler · `fast` in-process LRU/TTL/rate windows                                                                                                     |
| values    | `json` orjson, pointers, patches, portable Schema · `parse` loose input to types · `string` text verbs, safety, folding, chunks · `number` math, formats, vectors · `array` collections, search, ranking · `date` moments, parser, calendar · `rand` uuid7, tokens, fakes |
| mechanics | `func` call, memo, retry, limit · `thread` gather, offload, tasks, shutdown, sandboxed commands · `config` env layers and typed settings · `validate` pydantic shapes and the rulebook · `crypto` argon2, Fernet, keys · `token` JWT · `adapter` the provider contract    |
| io        | `fs` paths, files, drivers (local, S3), sandboxed extraction · `net` client, SSE, egress, probes · `storage` named disks · `assets` stamped public files · `view` Jinja · `cache` stores, locks, tags                                                                     |
| data      | `database` SQLAlchemy Core: pool, migrations DSL, ORM, query, outbox, documents, RLS, provisioning                                                                                                                                                                        |
| messaging | `broker` RabbitMQ and memory · `queue` jobs and workers · `event` bus · `schedule` cron and tasks · `socket` WebSocket hub · `broadcast` channels over Redis                                                                                                              |
| http      | `http` the app over FastAPI/Granian: route DSL, binder, request, one Response, envelope, throttle, trace · `health` checks and the heartbeat · `cli` command DSL                                                                                                          |
| providers | `mail` (log, Mailgun) · `sms` (log, Twilio, WhatsApp, Telegram) · `gateway` (Stripe, PayPal, PayTabs, Paymob, Sandbox) · `domain` (Cloudflare, Vercel) · `llm` models, prompts, sessions, memory · `rag` index, retriever, writer, judge                                  |
| proof     | `test` expect, client, sockets, samples, relay, stage, bench                                                                                                                                                                                                              |

## Tests and benches

- Flat, brutal, few, written on `engine.test` (`expect`, `test.fails`, `test.rejects`, `test.client`, `test.sockets`, `sample`), no bare `assert`, no `pytest.raises`; real `engine_test`, real Redis and RabbitMQ; third-party wires through `net.mocked` with the exact formats; `test_contracts.py` validates every adapter request against the providers' official specs when `CONTRACT_SPECS` is set; `test_live.py` and the live sections skip without their `LIVE_*`/`*_LIVE_*` keys and refuse anything but sandboxes.
- Each `bench_<name>.py` prints throughput and p50/p95/p99 and exits non-zero on an unexpected status or a blown budget; micro work is measured in CPU time and re-measured (`BENCH_REPEATS`), wall work scaled by `BENCH_SCALE`.

## How to add

- **A verb**: in its domain, a flat file ≤ 300 lines (a mixin when it grows), exported by the facade, pinned in the domain's test file, benched when hot.
- **A domain**: `src/<name>/pyproject.toml` (`engine-<name>`, its engine and library deps pinned), `src/<name>/engine/<name>/{__init__.py,py.typed,…}`, the facade dependency and workspace source in the root, `uv lock`; the manifest and shape laws refuse anything less.
- **A provider**: one `Adapter` subclass behind its family's manager with declared capabilities and a driver key, a log/memory implementation for tests, the real one proven against the service or its exact wire; every missing capability has a failing test naming its `Fault`.

## Traps

- pydantic-settings merges one field per nested model; kreuzberg's default config OCRs images (never send it images); pypdfium2 lacks `py.typed`; RUF001 flags Arabic beside ASCII escapes; PyAV seeks land on keyframes; Python 3.15 `lazy import` satisfies ruff and mypy.
- A module named like a singleton shadows it; a model field named `key` collides with `Model.key()`.
- The migrator ledger is shared per table: pin a batch relative to the status read first.
- mypy sees the namespace only with `explicit_package_bases` and one `mypy_path` entry per member; a new member joins `mypy_path`.
