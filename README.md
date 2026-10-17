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

| Part     | What it is                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Gate                                                                                    |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `api/`   | Python 3.15 + FastAPI on uv, everything under `src/`. A generic `core/` engine of 30 domains (http with a route DSL and throttle, assets served from `src/public` with content stamps, database on SQLAlchemy Core with a migration DSL and a generative ORM, a WebSocket hub with channel broadcasting, queue and event over RabbitMQ or in process, cache over Redis or in memory, schedule, storage with local and S3 disks, config with env layers, exceptions, crypto, token, mail, view, validate, json, …) under a Laravel-shaped app: enums → utils (dna, bases) → models → repositories → services → controllers · jobs · events · listeners · mails → routes (api, channel, events, schedule) → views, glued by `bootstrap/`. | `uv run ruff check`, `uv run mypy`, `uv run pytest`, `uv run python -m bootstrap check` |
| `infra/` | One bash bundle that carries the whole platform onto any Linux box over ssh as a Docker Compose monolith: nginx (TLS 1.2/1.3, HTTP/2 and HTTP/3, post-quantum hybrid key exchange, HSTS, per-client rate limits, edge cache), the api with its worker and scheduler, one image per web spec, PostgreSQL 18, RabbitMQ 4 and Redis 8 on an internal network, backups, systemd units, Let's Encrypt through http-01 or Cloudflare dns-01 (wildcard) when a token exists, Cloudflare DNS on the same condition, zero-downtime rolls and rollback. `production` and `staging` stacks.                                                                                                                                                        | `bash src/main.sh test --check`                                                         |
| `web/`   | One Next.js engine on Bun. Each spec under `specs/` chooses its `output` (`export` or `standalone`) and how each screen renders; indexing is derived from behavior, never a flag: a public server-rendered screen is indexed, a client-rendered or gated screen is not. `super` and `admin` are client-only exports, `client` is a server-rendered, indexable site.                                                                                                                                                                                                                                                                                                                                                                     | `bun run check`, `bun run typecheck`, `bun test`, `bun run build`                       |

Every network, file, process and third-party access in the api lives in `core/`; the layers above it are thin pipelines. In the web, markup lives only in `elements/`, specs are declarative data, and an analyzer enforces the layer order, the import rules and a 150-column line law.

---

## 🧠 Engineering

- One envelope on the wire: `data message errors code reason meta.request_id`, with a request id on every answer and every log line.
- Boundaries are enforced by tests, lints and CI, never by documentation alone: strict mypy, ruff with every rule on, Biome, an import analyzer, and markup render tests.
- Settled decisions stay settled; a change needs evidence. Performance claims come with a measurement.
- Zero comments in code: a name that needs a comment is renamed.

---

## ⚡ Performance

Measured on 2026-10-17 on a development machine, in process, not a benchmark of production hardware:

| Measurement                                                       | Result                           |
| ----------------------------------------------------------------- | -------------------------------- |
| api boot (pool + migrations + schema warm + two warm requests)    | 73 ms                            |
| `GET /v1/hello` through PostgreSQL, 3000 requests, concurrency 16 | 640 rps, p50 20 ms, p99 37 ms    |
| `GET /v1/auth/me` (JWT verify + user + roles), concurrency 8      | 280 rps, p50 24 ms               |
| JWT issue / verify, in process                                    | 19,000 / 13,000 per second       |
| WebSocket fan-out, one publish to 2,000 subscribed sockets        | 670,000 frames per second        |
| Queue push + run, event dispatch, in process                      | 52,000 / 67,000 per second       |
| web first-load JavaScript of the admin export                     | 216 KB over the wire with brotli |

---

## 🛡️ Security

- Typed faults everywhere: database and framework errors are translated into the one envelope, and unexpected exceptions never leak their message.
- Security headers and a Content Security Policy on every web answer, derived from the compiled spec; CORS allows only the configured browser origins.
- Supply chain: hash-pinned GitHub actions and container images, dependency review, gitleaks, trivy, syft and zizmor in the global workflow; Dependabot per ecosystem.
- Secrets never enter the repository: parts read `.env` and `.secret` files that are ignored; the infra resolves secrets from flags, the process environment, `JSON_ENV` or config files, renders them into private env files on the box, refuses quotes and placeholders that would leak literally, and never writes an ACL or a DNS token to disk.
- The deployed stack runs every container with dropped capabilities, no privilege escalation and a read-only root; the data services live on an internal network, PostgreSQL admits the app role over scram only, the superuser never logs in over the network, Redis runs under an ACL with the default user disabled, and nginx drops unknown names before a TLS handshake.

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
cd infra && bash src/main.sh test --check                                              # the infra gate: shellcheck, laws, docker compose and nginx accept the stack
cd infra && bash src/main.sh -s production --config ~/.ragx/production.env -y server deploy   # any linux box becomes the platform
cd infra && bash src/main.sh -s production --config ~/.ragx/production.env ci release         # build, prove, push, scan, roll, verify
```

PostgreSQL, Redis and RabbitMQ run locally as native services; the api reads its database from `DB_*` variables, its brokers from `QUEUE_URL`, `EVENT_URL` and `CACHE_URL`, and its signing secret from `AUTH_SECRET`, the same names the infra renders into the api env on the box. The web images are built per spec with `SPEC_API_URL` naming the deployed api origin. See [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).

---

## 📜 License

Copyright © 2026 Abdulrahman Yasser (comstrx).

Licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
