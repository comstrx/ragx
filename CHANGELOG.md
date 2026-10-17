# Changelog

Every release of RagX, one section per tag, one block per part.

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
