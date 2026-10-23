# ✨ RagX

<div align="center">
  <br/>
  <img height="150" src="https://github.com/user-attachments/assets/da98d0fa-d75b-4d88-8787-ab40095c8639"/>
  <br/>
  <br/>
</div>

[![Python + FastAPI](https://img.shields.io/badge/Python_%2B_FastAPI-AI_Platform-0D9488?logo=python&logoColor=white)](https://github.com/comstrx/ragx)
[![CI](https://github.com/comstrx/ragx/actions/workflows/global.yml/badge.svg?branch=main)](https://github.com/comstrx/ragx/actions/workflows/global.yml)
[![Release](https://img.shields.io/github/v/release/comstrx/ragx?sort=semver)](https://github.com/comstrx/ragx/releases/latest)
[![License](https://img.shields.io/badge/License-Apache_2.0-007EC6)](https://github.com/comstrx/ragx/blob/main/LICENSE)

> **One AI Platform. Every Tenant. Any Model. Infinite Possibilities.**

RagX is an independent **multi-tenant AI platform** designed for intelligent conversations, human support, context orchestration, cloud and local LLMs, and retrieval-augmented generation — accessible through secure APIs and developer-friendly SDKs.

**Build intelligence once. Bring it to every application.**

---

## 🎯 Overview

RagX is a third-party service: tenants integrate through the API only, and no client code or data lives in this repository. The repository holds two layers governed by one set of root rules: `engine/`, the generic foundations that carry every integration and know no product, and `product/`, RagX itself. Each folder below them is an independent workspace with its own manifest, lockfile, tests and gate; the engines are consumed by local path today and can leave for their own repositories, consumed by release, without touching a line of the product.

The api's first real release (v1.0.0) shipped the engine, not a product: an enterprise Python engine proven on real PostgreSQL + pgvector, Redis, RabbitMQ and llama.cpp models, under an empty, law-checked Laravel-shaped application that serves only `/health`, the docs and the assets. The business that exercised it (tenants, roles, auth, AI and human conversations, per-tenant retrieval) was built, proven end to end and removed; what it taught lives in the engine, and the next product layer starts from a clean `app/`.

---

## 🧩 Capabilities

Planned and phased; nothing below is shipped yet beyond the skeleton:

- Multi-tenant conversations with `ai`, `human` and `hybrid` modes and human handoff.
- Multi-provider LLM orchestration (cloud and local models) behind one adapter.
- Context engineering per tenant, department or tag, and retrieval-augmented generation on indexed tenant data.
- Super and admin panels, tenant-facing sites, and a realtime chat surface for end users.

---

## 🏗️ Architecture

```
ragx/
├── skill/              the operating contract every agent and engineer loads first
├── engine/
│   ├── python/         the server engine: a uv workspace of 42 domain packages under the `engine` namespace
│   └── bun/            the TypeScript engine: one package `engine`, one subpath per member
└── product/
    ├── api/            the RagX application over engine/python
    ├── infra/          the platform carrier
    ├── web/            the panels and the SEO site over engine/bun (Next.js)
    └── mobile/         the role apps over engine/bun (Expo)
```

| Part             | What it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Gate                                                                                    |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `engine/python`  | Python 3.15, a uv workspace: 42 domain packages (`engine-http`, `engine-database` …) under the `engine` namespace and an `engine` facade over all of them, each declaring exactly the domains and pinned libraries it imports: row-level security in the schema DSL with per-transaction tenant binding, SSRF-safe egress, recovery from Postgres, Redis and RabbitMQ outages, http with a route DSL, database on SQLAlchemy Core with a migration DSL and a generative ORM, a WebSocket hub with broadcasting, queue and events over RabbitMQ or in process, cache, schedule, storage, llm adapters (a local server, ChatGPT, Claude, Gemini, DeepSeek) under one prompt and session DSL, sandboxed extraction, retrieval, config, faults, crypto, token, mail, view, validate, parse, json, health. | `uv run ruff check`, `uv run mypy`, `uv run pytest`                                     |
| `engine/bun`     | Bun and TypeScript. One package, `engine`, whose members (`api client spec screen translate validate state storage world tooling …`) run on the browser, Bun, Node and Hermes alike; only `tooling` touches the runtime, and DOM mechanics live in `interact`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | `bun run check`, `bun run lint`, `bun test`, `bun audit`                                |
| `product/api`    | The RagX application, flat at its root (`app bootstrap config database routes views public storage tests benches`): an empty Laravel-shaped app whose layers wait for the product (enums → utils (dna, bases) → models → repositories → services → controllers · jobs · events · listeners · mails → routes (api, channel, events, schedule) → views), configured by `config/` and glued by `bootstrap/`, which owns `/health` and `provision`.                                                                                                                                                                                                                                                                                                                                                       | `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run python -m bootstrap check` |
| `product/infra`  | One self-contained Bash 5 bundle: a flat generic core, one module per tool, a single env schema and a bootstrap that assembles the selected stack. The native stack runs Docker Compose with a persistent HAProxy 3.4 edge (HTTP/1.1, HTTP/2, frontend HTTP/3 over QUIC, Docker DNS discovery, readiness gating, passive circuit breaking) and a Portainer CE GitOps control plane, with blue/green releases, draining, rollback, locks and recorded phases, and self-hosted models (Text Embeddings Inference, llama.cpp) pinned file by file and served offline on an internal network.                                                                                                                                                                                                             | `bash src/main.sh test --check`                                                         |
| `product/web`    | One Next.js surface engine. Each spec under `specs/` chooses its `output` (`export` or `standalone`), its `localization` and how each screen renders; indexing is derived from behavior, never a flag. Every feature is one contract (`transport` and `view`) over flat, token-styled Tailwind elements and components whose import laws the analyzer enforces. `super` and `admin` are client-only exports, `client` is a static, server-rendered, indexable site.                                                                                                                                                                                                                                                                                                                                   | `bun run check`, `bun run typecheck`, `bun test`, `bun run deliver --all`               |
| `product/mobile` | One Expo and React Native surface engine with the same layers, specs and feature contracts as the web, its own router-free navigator, Metro guards that keep one copy of every host package, and Hermes bytecode per spec (`admin`, `client`).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | `bun run check`, `bun run typecheck`, `bun test`, `bun run export --all`                |

Every network, file, process and third-party access lives in an engine; the product layers above it are thin pipelines. In the web and the mobile, markup and styles live only in `elements/`, specs are declarative data, and an analyzer enforces the layer order, the import rules, the token-only class law and a 150-column line law; `bun run audit` weighs every build against its brotli budgets and checks what crawlers see.

Infrastructure keeps `src/core/`, `src/config/`, `src/bootstrap/` and `src/module/` flat; `bootstrap/index.sh` is the only entry and loads `app/<stack>/` from `Bash.toml`. Laws checked on every file enforce the layer calls, names, the hand style, zero comments and `err`/`return` error handling. See [the infra contract](skill/infra.md).

HAProxy 3.4.7 LTS and Portainer CE 2.45.2 LTS are pinned by digest. `HTTP3_ENABLED=true` (the default, requiring `TLS_ENABLED=true`) adds QUIC on the frontend with Alt-Svc and TCP fallback; backends stay HTTP/1.1 and 0-RTT is off. Engineering constants live in `Bash.toml [native]`; the env file carries replicas, strategy, domains, health paths, secrets and integrations.

The [runbook](skill/infra.md#runbook) covers setup, first deployment and rollback. The [lab evidence](product/infra/benches/results.json) records a 2026-10-19 run on a 4 vCPU rootless-Docker host: HTTP/3 200 through the published UDP port, HTTP/2 vs HTTP/3 latency, CPU and throughput, zero failed requests across 150,000 requests during a blue/green switch and 60,000 during rollback, scaling and replica crash under load, a rejected candidate, live-session draining and a 50,000-row backup restore. A GitHub Actions run in a private repository proves private GHCR push and pull and Portainer GitOps from a private repository with a token read from the environment, S3 backup upload, the ACME challenge route, and HTTP/3 keeping 1.3x to 1.7x HTTP/2 throughput under 1% to 3% emulated loss. It is bounded acceptance evidence, not a production capacity guarantee, and it lists what stays unverified.

---

## 🧠 Engineering

- One envelope on the wire: `data message errors code reason meta.request_id`, with a request id on every answer and every log line.
- Boundaries are enforced by tests, lints and CI, never by documentation alone: strict mypy, ruff with every rule on, Biome, an import analyzer, and markup render tests.
- Settled decisions stay settled; a change needs evidence. Performance claims come with a measurement.
- Zero comments in code: a name that needs a comment is renamed.
- Every agent and engineer starts at [AGENTS.md](AGENTS.md), which points to [`skill/`](skill/index.md): the vision, the stack, the style, the way of working and the laws of each part, self-contained and binding.

---

## ⚡ Performance

Measured on 2026-10-19 on a development machine (8 cores, shared with other work: load average 1–3), in process with the `engine/python` and `product/api` bench suites, not a benchmark of production hardware. The hello and auth figures come from small bench apps mounted on the bare framework (`benches/bench_hello.py`, `benches/bench_auth.py`), doing the same work the removed product routes did:

| Measurement                                                                                   | Result                               |
| --------------------------------------------------------------------------------------------- | ------------------------------------ |
| api boot in a warm process (`product/api` `bench_boot`, 7 cycles: create · ready · shutdown)  | 6 ms · 25 ms median (22–31) · 7–9 ms |
| first burst of 8 concurrent `/health` requests right after boot                               | slowest 25 ms                        |
| `GET /v1/hello` (shape validation + one PostgreSQL lookup), 3000 requests, conc. 16           | 485 rps, p50 26 ms, p99 61 ms        |
| `GET /v1/auth/me` (JWT verify + one row), 3000 requests, concurrency 8                        | 451 rps, p50 15 ms, p99 46 ms        |
| refresh-token rotation in one transaction / argon2 login                                      | p50 7 ms / p50 513 ms                |
| JWT issue / verify, in process                                                                | 11,700 / 9,350 per second            |
| WebSocket fan-out, one publish to 2,000 subscribed sockets                                    | 455,000 frames per second            |
| Queue push + run, event dispatch, in process                                                  | 11,300 / 21,700 per second           |
| hybrid retrieval over 5,000 pgvector rows (HNSW plan)                                         | p50 16 ms, p99 29 ms                 |
| local models on llama.cpp, CPU, 2 threads each: query embedding · rerank 10 · 32-token answer | p50 545 ms · 4.2 s · 4.3 s           |
| exact token count through the model's own tokenizer                                           | p50 5.7 ms                           |
| web first load of the admin export / the client site, JavaScript + CSS (2026-10-19)           | 197 + 10 KB / 197 + 10 KB brotli     |

Every bench fails on an unexpected status or a blown p99 budget; `BENCH_SCALE` widens the budgets on a busy machine. Run `uv run python -m benches.bench_<name>` in `engine/python/` to reproduce; `bench_models` runs only when `RAG_LIVE_*` point at live model servers.

---

## 🛡️ Security

- Row-level security is the second wall behind application scoping: tables declared `isolated()` force a fail-closed policy, the tenant is bound per transaction, and `python -m bootstrap provision` creates the runtime role without `SUPERUSER` or `BYPASSRLS` (boot warns otherwise).
- Every user-supplied URL is fetched through an SSRF-safe egress: public addresses only, the connection pinned to the checked address, each redirect checked again, no environment proxies.
- Typed faults everywhere: database and framework errors are translated into the one envelope, and unexpected exceptions never leak their message.
- The api trusts `X-Forwarded-For` only through the configured proxies, sends `Retry-After` with every `429`, and never echoes a path or user input in a fault reason; a lost broker, cache or database connection is a typed fault that heals, never a silent loss.
- Security headers and a Content Security Policy on every web answer, derived from the compiled spec; CORS allows only the configured browser origins.
- Supply chain: hash-pinned GitHub actions and container images, dependency review, gitleaks, trivy, syft and zizmor in the global workflow; Dependabot per ecosystem.
- Secrets stay in ignored runtime files. Infra uses one env schema, parses values as data, redacts sensitive output and renders service env files with mode `0600`; distributable bundles contain safe defaults and templates only.
- The deployed stack runs every container with dropped capabilities, no privilege escalation and a read-only root; the data services live on an internal network, PostgreSQL admits the app role over scram only, the superuser never logs in over the network, Redis runs under an ACL with the default user disabled, and HAProxy requires matching TLS SNI, verifies backend readiness and keeps its control sockets private. Self-hosted models load only files pinned by SHA-256 (pickle formats refused) and run offline as nobody on an internal network without egress.

See [SECURITY.md](SECURITY.md) for reporting a vulnerability.

---

## 🧪 Development

```bash
cd engine/python && uv sync --locked --python 3.15 && uv run pytest              # the engine against the real services
cd engine/python && uv run python -m benches.bench_hello                          # benches bite on any error
cd engine/bun && bun install && bun link && bun test                              # the TypeScript engine, linked for the surfaces
cd product/api && uv sync --locked --python 3.15 && uv run python -m bootstrap     # serve on 127.0.0.1:8000
cd product/api && uv run python -m bootstrap provision && uv run python -m bootstrap migrate   # role, database, extensions, then schema
cd product/api && uv run python -m bootstrap work                                 # queue workers, no http
cd product/web && bun install && bun run dev                                       # the first installed spec
cd product/web && bun run deliver --all                                             # build and audit every spec
cd product/web && NEXT_PUBLIC_SPEC=client bun run deliver && bun run start         # the indexable site, audited and served
cd product/mobile && bun install && bun run start                                  # Expo for the first installed spec
cd product/mobile && bun run export --all                                          # Hermes bytecode for every spec
cd product/infra && bash src/main.sh test --check                                 # offline Bash, ShellCheck and structural checks
cd product/infra && bash src/main.sh build-release                               # production-mode bundle and checksum
cd product/infra && bash src/main.sh --config ~/.ragx/staging.env plan
```

PostgreSQL, Redis and RabbitMQ run locally as native services; the api reads its database from `DB_*` variables, its brokers from `QUEUE_URL`, `EVENT_URL` and `CACHE_URL`, and its signing secret from `AUTH_SECRET`, the same names the infra renders into the api env on the box. Every surface is its own part with its own image, domains and replicas, declared once in `product/infra/src/config/parts.sh` (api, super, admin, supplier, vendor, delivery, client, tenant); RagX builds api, super and tenant today; the site images bake `SPEC_API_URL`, the deployed api origin. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).

---

## 📜 License

Copyright © 2026 Abdulrahman Yasser (comstrx).

Licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
