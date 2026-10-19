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
<img width="2172" height="724" alt="logo" src="https://github.com/user-attachments/assets/da98d0fa-d75b-4d88-8787-ab40095c8639" />

> **One AI Platform. Every Tenant. Any Model. Infinite Possibilities.**

RagX is an independent **multi-tenant AI platform** designed for intelligent conversations, human support, context orchestration, cloud and local LLMs, and retrieval-augmented generation — accessible through secure APIs and developer-friendly SDKs.

**Build intelligence once. Bring it to every application.**

---

## 🎯 Overview

RagX is a third-party service: tenants integrate through the API only, and no client code or data lives in this repository. The repository holds the three parts of the platform, each with its own toolchain, tests and gate, governed by one set of root rules.

The current release proves the skeleton end to end with one lifecycle: a browser feature calls `GET /v1/hello`, the request crosses every api layer down to a PostgreSQL table, and the answer renders in a static admin panel and in a server-rendered, indexable site.

---

## 🧩 Capabilities

Planned and phased; nothing below is shipped yet beyond the skeleton:

- Multi-tenant conversations with `ai`, `human` and `hybrid` modes and human handoff.
- Multi-provider LLM orchestration (cloud and local models) behind one adapter.
- Context engineering per tenant, department or tag, and retrieval-augmented generation on indexed tenant data.
- Super and admin panels, tenant-facing sites, and a realtime chat surface for end users.

---

## 🏗️ Architecture

| Part     | What it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Gate                                                                                    |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `api/`   | Python 3.15 + FastAPI on uv, everything under `src/`. A generic `core/` engine of 34 domains (http with a route DSL, a payload DSL, named urls, SSE and a throttle, health checks, assets served from `src/public` with content stamps, database on SQLAlchemy Core with a migration DSL and a generative ORM, a WebSocket hub with channel broadcasting, queue and event over RabbitMQ or in process, cache over Redis or in memory, schedule, storage with local and S3 disks, llm adapters (a local server, ChatGPT, Claude, Gemini, DeepSeek) under one prompt and session DSL, config with env layers, error and exception handling, crypto, token, mail, view, validate with a Laravel-style rules engine, parse, json with pointers and patches, …) under a Laravel-shaped app: enums → utils (dna, bases) → models → repositories → services → controllers · jobs · events · listeners · mails → routes (api, channel, events, schedule) → views, glued by `bootstrap/`. | `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run python -m bootstrap check` |
| `infra/` | One self-contained Bash 5 bundle: a flat generic core, one module per tool, a single env schema and a bootstrap that assembles the selected stack. The native stack runs Docker Compose with a persistent HAProxy 3.4 edge (HTTP/1.1, HTTP/2, frontend HTTP/3 over QUIC, Docker DNS discovery, readiness gating, passive circuit breaking) and a Portainer CE GitOps control plane, with blue/green releases, draining, rollback, locks and recorded phases.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | `bash src/main.sh test --check`                                                         |
| `web/`   | One Next.js engine on Bun. Each spec under `specs/` chooses its `output` (`export` or `standalone`) and how each screen renders; indexing is derived from behavior, never a flag: a public server-rendered screen is indexed, a client-rendered or gated screen is not. `super` and `admin` are client-only exports, `client` is a server-rendered, indexable site.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | `bun run check`, `bun run typecheck`, `bun test`, `bun run build`                       |

Every network, file, process and third-party access in the api lives in `core/`; the layers above it are thin pipelines. In the web, markup lives only in `elements/`, specs are declarative data, and an analyzer enforces the layer order, the import rules and a 150-column line law.

Infrastructure keeps `src/core/`, `src/config/`, `src/bootstrap/` and `src/module/` flat; `bootstrap/index.sh` is the only entry and loads `app/<stack>/` from `Bash.toml`. Laws checked on every file enforce the layer calls, names, the hand style, zero comments and `err`/`return` error handling. See [the infra contract](skill/infra.md).

HAProxy 3.4.7 LTS and Portainer CE 2.45.2 LTS are pinned by digest. `HTTP3_ENABLED=true` (the default, requiring `TLS_ENABLED=true`) adds QUIC on the frontend with Alt-Svc and TCP fallback; backends stay HTTP/1.1 and 0-RTT is off. Engineering constants live in `Bash.toml [native]`; the env file carries replicas, strategy, domains, health paths, secrets and integrations.

The [runbook](skill/infra.md#runbook) covers setup, first deployment and rollback. The [lab evidence](infra/benches/results.json) records a 2026-10-19 run on a 4 vCPU rootless-Docker host: HTTP/3 200 through the published UDP port, HTTP/2 vs HTTP/3 latency, CPU and throughput, zero failed requests across 150,000 requests during a blue/green switch and 60,000 during rollback, scaling and replica crash under load, a rejected candidate, live-session draining and a 50,000-row backup restore. A GitHub Actions run in a private repository proves private GHCR push and pull and Portainer GitOps from a private repository with a token read from the environment, S3 backup upload, the ACME challenge route, and HTTP/3 keeping 1.3x to 1.7x HTTP/2 throughput under 1% to 3% emulated loss. It is bounded acceptance evidence, not a production capacity guarantee, and it lists what stays unverified.

---

## 🧠 Engineering

- One envelope on the wire: `data message errors code reason meta.request_id`, with a request id on every answer and every log line.
- Boundaries are enforced by tests, lints and CI, never by documentation alone: strict mypy, ruff with every rule on, Biome, an import analyzer, and markup render tests.
- Settled decisions stay settled; a change needs evidence. Performance claims come with a measurement.
- Zero comments in code: a name that needs a comment is renamed.
- Every agent and engineer starts at [AGENTS.md](AGENTS.md), which points to [`skill/`](skill/index.md): the vision, the stack, the style, the way of working and the laws of each part, self-contained and binding.

---

## ⚡ Performance

Measured on 2026-10-19 on a development machine (8 cores, load average 0.5–1.0), in process with the `api/benches` suite, not a benchmark of production hardware:

| Measurement                                                                       | Result                                 |
| --------------------------------------------------------------------------------- | -------------------------------------- |
| api boot in a warm process (`bench_boot`, 7 cycles: create · ready · shutdown)    | 6 ms · 35 ms median (34–45) · 4–11 ms  |
| first burst of 8 concurrent requests right after boot                             | slowest 32 ms                          |
| `GET /v1/hello` through PostgreSQL, 3000 requests, concurrency 16                 | 499 rps, p50 27 ms, p99 47 ms          |
| `GET /v1/auth/me` (JWT verify + user + roles), 3000 requests, concurrency 8       | 242 rps, p50 30 ms, p99 47 ms          |
| JWT issue / verify, in process                                                    | 18,200 / 11,700 per second             |
| WebSocket fan-out, one publish to 2,000 subscribed sockets                        | 588,000 frames per second              |
| Queue push + run, event dispatch, in process                                      | 18,600 / 33,900 per second             |
| web first-load JavaScript of the admin export (2026-10-17)                        | 216 KB over the wire with brotli       |

Queue and event figures dropped from the 2026-10-17 run (52,000 / 67,000) because every job now carries its request context, leaves only after the commit and crosses the broker as JSON, and every dispatch keeps its history; the budgets in `api/benches` hold. Run `uv run python -m benches.bench_<name>` in `api/` to reproduce.

---

## 🛡️ Security

- Typed faults everywhere: database and framework errors are translated into the one envelope, and unexpected exceptions never leak their message.
- The api trusts `X-Forwarded-For` only through the configured proxies, sends `Retry-After` with every `429`, rotates a refresh token at most once under a race, spends the same argon2 work for unknown and known emails, and never echoes a path or user input in a fault reason.
- Security headers and a Content Security Policy on every web answer, derived from the compiled spec; CORS allows only the configured browser origins.
- Supply chain: hash-pinned GitHub actions and container images, dependency review, gitleaks, trivy, syft and zizmor in the global workflow; Dependabot per ecosystem.
- Secrets stay in ignored runtime files. Infra uses one env schema, parses values as data, redacts sensitive output and renders service env files with mode `0600`; distributable bundles contain safe defaults and templates only.
- The deployed stack runs every container with dropped capabilities, no privilege escalation and a read-only root; the data services live on an internal network, PostgreSQL admits the app role over scram only, the superuser never logs in over the network, Redis runs under an ACL with the default user disabled, and HAProxy requires matching TLS SNI, verifies backend readiness and keeps its control sockets private.

See [SECURITY.md](SECURITY.md) for reporting a vulnerability.

---

## 🧪 Development

```bash
cd api && uv sync --locked --python 3.15 && uv run python -m bootstrap        # serve on 127.0.0.1:8000
cd api && uv run python -m bootstrap migrate && uv run python -m bootstrap seed
cd api && uv run python -m benches.bench_hello && uv run python -m benches.bench_socket   # benches bite on any error
cd api && uv run python -m bootstrap work                                              # queue workers, no http
cd web && bun install && bun run dev                                          # the first installed spec
cd web && NEXT_PUBLIC_SPEC=client bun run build && bun run start              # the indexable site
cd infra && bash src/main.sh test --check                                    # offline Bash, ShellCheck and structural checks
cd infra && bash src/main.sh build-release                                  # production-mode bundle and checksum
cd infra && bash src/main.sh --config ~/.ragx/staging.env --environment staging plan
```

PostgreSQL, Redis and RabbitMQ run locally as native services; the api reads its database from `DB_*` variables, its brokers from `QUEUE_URL`, `EVENT_URL` and `CACHE_URL`, and its signing secret from `AUTH_SECRET`, the same names the infra renders into the api env on the box. The web images are built per spec with `SPEC_API_URL` naming the deployed api origin. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).

---

## 📜 License

Copyright © 2026 Abdulrahman Yasser (comstrx).

Licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
