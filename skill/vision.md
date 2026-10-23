# Vision

RagX is an independent multi-tenant AI platform: AI, human and hybrid conversations, multi-provider LLM orchestration, per-tenant context engineering, and retrieval-augmented answers over indexed tenant data. It is a third-party service: tenants integrate only through the API; no client code or data lives here. The only API contract is the OpenAPI the api generates; web and mobile consume it, nothing else is promised.

## Layout

| Folder           | Role                                                                                                                                                     |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `engine/python`  | Owns every server integration: http, database, broker, cache, storage, llm, retrieval, extraction, security. Product-free.                               |
| `engine/bun`     | Owns every client mechanism: api client, contracts, specs, screens, state, translation, world data, tooling. Product-free, any runtime.                  |
| `product/api`    | The backend: a thin Laravel-shaped application over engine/python.                                                                                       |
| `product/web`    | The browser surfaces: super panel, admin panels, the tenant-facing indexable site; Next.js over engine/bun.                                              |
| `product/mobile` | The phone surfaces for the roles that need native reach (push, background audio, voice, calls); Expo over engine/bun, the web's contracts word for word. |
| `product/infra`  | The carrier: one Bash bundle that turns any Linux box into the whole stack (Compose, HAProxy edge, blue/green, backups, TLS, DNS).                       |

`engine/` never imports `product/`. Engines are consumed by local path today (`uv` path source, `link:engine`) and are built to leave for their own repositories and be consumed by release with one changed line per consumer.

## Doctrine

- **Gravity.** Logic sinks to the lowest layer able to carry it. A leaf never grows a loop, retry, parser, format, protocol detail or provider call; it calls an engine verb.
- **Engines keep training.** They are never finished: a real requirement that reveals a missing primitive extends the engine first, with its test. The measure of a change is how little lands above the engine.
- **One owner.** A second retry, slug, date format, encoder, client, cache or header is a defect, however small. Product rules stay in the product; configuration in `config/`, specs and env examples.
- **One direction.** Engines import themselves and their libraries; product layers import their engine and lower layers; product parts meet only through contracts (OpenAPI, env names, image tags). Cycles are refused by tests.
- **One type, one error, one log, one envelope.** Unified types from the engine; one typed fault, one code set, one handler, no leaked exception message; structured `domain.verb` logs with a request id everywhere; `data message errors code reason meta.request_id` on the wire.
- **Security by design.** Server-side authorization, tenancy and scoping on every resource; prompts are never a boundary; inputs validated at the boundary; secrets injected, never embedded; least-privilege containers; hardened TLS and headers.
- **Measured performance.** A claim is a bench number with p50/p95/p99 on a stated machine; budgets live in the benches; optimization follows a profile, in the engine, once.

## Tenancy

- Tenants are client businesses: `tenants.type` is `platform` (exactly one, created by bootstrap) or `workspace`. Every row carries `tenant_id`, users and roles included; PostgreSQL RLS is the second wall and the runtime role cannot bypass it.
- **Super panel** (platform tenant): tenants (info, allowed hosts, keys, settings, permissions, scopes), global settings, statistics, support chat with tenant admins (the only cross-tenant conversation).
- **Admin panel** (per workspace): statistics, users and roles, settings, chat with its customers, context engineering per department or tag, later retrieval data.
- **Roles** are `admin` and `client` only; `super` and `supervisor` are boolean flags on the role row.
- **Client provisioning**, idempotent, `users.role = client` with optional `ref_id` (the user's id on the tenant's site): manual add; automatic on a tenant-side conversation start; bulk `users.sync` with the fixed payload `name email phone country city lng lat avatar tags[] scopes[] settings{}` (absent keeps, explicit `null` clears, capped batches, a result per user).
- **Identity uniques**, partial (`deleted_at IS NULL AND <col> IS NOT NULL`): `(tenant_id, role, email|phone|ref_id)`. Matching ref → email → phone; `ref_id` is stamped once, only from tenant server channels, only onto a null `ref_id`; a different one is a conflict, never a merge.
- **Auth**: tenants use the api key + secret the super panel mints (`Authorization`); panel users JWT access + rotated refresh; allowed hosts gate browser origins.

## AI

- A provider adapter (OpenAI, Claude, Gemini, DeepSeek; local through any OpenAI-compatible server, vLLM for GPU) × a conversation strategy: `persistent` (provider session + early compaction) or `stateless` (last N + summary).
- A deterministic budget decides compaction: U = H + R + S + Q + O against ~70% of the window; an LLM writes the summary. RagX owns conversations and memory; provider session ids are an optimization.
- `ContextProvider`: static now, retrieval later. Chat modes `ai human hybrid` with handoff; WebSocket for chat, SSE for streaming. No training: data is indexed (local embeddings, reranker, hybrid retrieval).

## Phasing

1 core + database + tenants → 2 LLMs + context + conversations → 3 realtime chat + human support → 4 panels and apps → 5 security, end-to-end, load → 6 RAG, last, after the journey is proven in production. Each phase ships verifiable increments through the full path (engine → api → web and mobile → infra).

## Settled

Everything here is settled. A change needs hard evidence that a decision is unsafe, impossible or inferior, raised as a question, never executed. Open items (exact role schema, tenant auth flow, provider surface, retrieval pipeline) settle at implementation and are recorded here.
