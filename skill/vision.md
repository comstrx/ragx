# Vision

RagX is an independent multi-tenant AI platform: AI chat, human support and hybrid conversations, multi-provider LLM orchestration, context engineering per tenant, and retrieval-augmented generation on indexed tenant data. It is a third-party service: tenants integrate only through the API, and no client code or data lives in this repository.

## The three parts

| Part     | Role                                                                                                                                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`   | The product. Python 3.15 + FastAPI on uv, PostgreSQL through SQLAlchemy Core + asyncpg, RabbitMQ for jobs and events, Redis for cache and throttling, a generic `core/` engine under a thin application.              |
| `web/`   | Every human surface. One Next.js engine on Bun: the super panel, the admin panels and the tenant-facing indexable sites, each a declarative spec over the same engine.                                                |
| `infra/` | The platform carrier. One bash bundle that turns any Linux box into the whole stack as a Docker Compose monolith: nginx, api, worker, scheduler, web images, PostgreSQL, RabbitMQ, Redis, backups, TLS, DNS, systemd. |

The only API contract is the OpenAPI document the api generates. The web consumes it; nothing else is promised.

## Architecture doctrine

**Gravity.** Logic sinks to the lowest layer able to carry it. When a leaf (a controller, a service, a feature, a module verb) needs a trick, the trick becomes a verb in the layer below, tested there, and the leaf calls it in one line. A leaf never grows a loop, a retry, a parser, a format, a protocol detail or a provider call of its own.

**Thin layers above a core that keeps training.** `api/src/core`, `web/src/lib/std` and `infra/src/core` own every integration: every third-party library, every network, file, process and provider access, every protocol. They are generic: no product name, no business rule, no tenant, no model, no migration. They are never finished: every real requirement that reveals a missing primitive extends the core first, with a test, and the layers above stay pipelines of one or two lines. The measure of a good change is how little code lands above the core.

**One owner per responsibility.** A capability has exactly one home. The second implementation of a retry, a slug, a date format, a json encoder, a client, a cache or a header is a defect, even when it is "small". Shared capabilities are centralized in the core of the part; product rules stay in the application layer; configuration stays in `config/`, specs and `.env.example`.

**Dependencies flow one way.** Core imports only core. Application layers import the core and themselves, never each other upward. Parts never import each other; they meet through contracts (the OpenAPI, environment names, image tags). Cycles are refused by tests.

**Unified typing.** One type for one idea across the whole part: `DateTime`, `TimeDelta`, `Uuid`, `Path`, `Decimal`, `JsonValue` come from the core, never from the standard library in the layers above. Public functions are fully typed; `Any` is contained at explicit boundaries; a protocol describes a port, a frozen dataclass describes a value, a pydantic model describes an untrusted boundary, an enum describes a closed vocabulary.

**Unified errors.** One typed fault, one code set, one handler. Database, framework, provider and unexpected errors are translated into the envelope with a code and a reason; the message of an unexpected exception never leaks; 5xx are reported with their cause and traceback, 4xx at debug. A layer above the core never catches a third-party exception type.

**Logs for everything, unified.** Structured events (`domain.verb`) with fields, a request id on every answer and every line, spans with durations around every boundary (boot, database, queue, provider), JSON in production. No bare prints, no string interpolation into messages.

**One envelope on the wire.** `data message errors code reason meta.request_id`, pagination in `meta`, rate limits in headers, a request id in headers. The web understands exactly this and nothing else.

**Security by design.** Authorization, tenancy and scoping are enforced server-side on every resource; prompts and harnesses are never a security boundary; inputs are validated at the boundary; secrets are injected, never embedded; every container runs least-privileged; every edge answers with hardened TLS and headers.

**Measured performance.** A claim is a number from a bench run on a stated machine and workload with p50/p95/p99. Budgets are enforced by the benches themselves (they fail on a blown p99 or any unexpected status). Optimization happens after a profile, in the core, once.

## Tenancy

- Multi-tenant means many client businesses. `tenants.type` is `platform` or `workspace`: exactly one platform tenant (created by bootstrap) and any number of workspaces.
- Every row carries `tenant_id`, users and roles included; platform staff live in the platform tenant. Row-level security is the second wall behind application scoping; the runtime database role cannot bypass it.
- **Super panel**: the platform tenant's panel. Tenants (info, allowed hosts, keys, settings, permissions, scopes), global settings and permissions, statistics, and a support chat with tenant admins: the only cross-tenant conversation.
- **Admin panel**: one per workspace. Statistics, users and roles, settings and permissions, chat with its customers, context engineering (harness and context prompts per department or tag), and later retrieval data.
- **Roles**: `admin` and `client` only (`client` = a tenant's customers). `super` and `supervisor` are boolean flags on the role row; a normal admin has both false. The super panel is a separate concept from the `super` flag.
- **Client provisioning**, three idempotent ways, each storing `users.role = client` and an optional `ref_id` (the user's id on the tenant's site): manual add in the admin panel; automatic creation when a conversation starts from the tenant side; a bulk `users.sync` endpoint for the tenant's backend with a fixed per-user payload (`name email phone country city lng lat avatar tags[] scopes[] settings{}`), where an absent field keeps the stored value, an explicit `null` clears it, batches are capped and report per user.
- **Identity uniques**, partial (`WHERE deleted_at IS NULL AND <col> IS NOT NULL`): `(tenant_id, role, email)`, `(tenant_id, role, phone)`, `(tenant_id, role, ref_id)`. Matching order ref → email → phone. `ref_id` is stamped once, only from tenant server channels, only onto a row whose `ref_id` is null; a different `ref_id` is a conflict, never a merge.
- **Auth**: tenants authenticate with the api key + secret the super panel mints, in the `Authorization` header; panel users with JWT access tokens and rotated refresh tokens; tenant allowed hosts gate browser origins; every end-user resource is authorized server-side.

## AI and conversation design

- An LLM provider adapter (cloud: OpenAI, Claude, Gemini, DeepSeek; local: Ollama, vLLM for GPU production) × a conversation strategy: `persistent` (provider session + early compaction) or `stateless` (last N messages + summary).
- A deterministic token budget decides compaction: U = H + R + S + Q + O against a configurable budget (~70%); an LLM writes the summary. RagX owns conversations and memory; provider session ids are an optimization.
- A `ContextProvider` protocol: static context now, retrieval later. Chat modes `ai / human / hybrid` with human handoff. WebSocket for chat, SSE for AI streaming.
- No model training: uploaded data is indexed (local embeddings, reranker, hybrid retrieval), never trained.

## Phasing

1. Core + database + tenants.
2. LLM providers + context + conversations.
3. Realtime chat + human support.
4. Panels.
5. Security, end-to-end, load.
6. RAG: ingestion, embeddings, hybrid retrieval. Last, and only after the earlier journey is proven in production.

Every phase ships verifiable increments through the full path (api → web → infra) rather than a wide layer at a time.

## Settled and open

Everything above is settled. A settled decision changes only with hard evidence that it is unsafe, impossible or objectively inferior, stated as a question to the owner, never executed as "my decision". Open items are decided at implementation time and recorded here when they settle: the exact role schema, the exact tenant auth flow, the provider adapter surface, the retrieval pipeline.
