# Stack

## Policy

- The newest stable release of every runtime, library, image and action on the day of the task; the manifests (`pyproject.toml`, `uv.lock`, `package.json`, `bun.lock`, `infra/.env.example`, the workflow pins) are ground truth. Freshness is checked against the official source, never assumed from memory.
- Mature libraries with native cores are preferred over custom code; custom engineering needs a measured advantage. A library that fails on the pinned runtime is replaced after it is actually installed and exercised on that runtime, never on hearsay.
- One strict type checker per language, one linter with every rule on, no code formatter for Python or TypeScript (the hand style in `style.md` is the format), Prettier for Markdown/YAML/JSON, taplo for TOML.

## Runtimes and tools

| Part     | Runtime and tools                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`   | CPython 3.15 (regular GIL build; the free-threaded build only as a measured experiment), uv (locked), FastAPI, granian, SQLAlchemy Core 2.x + asyncpg, pydantic 2 + pydantic-settings + python-dotenv, PyJWT, cryptography, argon2-cffi, Jinja2, aiosmtplib, httpx, orjson, structlog, obstore, python-multipart, aio-pika, redis; dev: ruff (`select = ["ALL"]`), mypy strict + pydantic plugin, pytest, httpx2 for Starlette's test client, watchfiles |
| `web/`   | Bun (package manager, tooling, release server), Node 26 (Next's build and standalone server), Next 16, React 19, zod 4, zustand 5, lucide-static, subset-font; dev: Biome (lint only, formatter off), TypeScript 7 strict, `bun test`, mitata for benches                                                                                                                                                                                                |
| `infra/` | bash 5, shellcheck, docker + the compose plugin, envsubst, jq, openssl, curl, ssh; the images it renders: `nginxinc/nginx-unprivileged` 1.29, `postgres` 18, `rabbitmq` 4.2-alpine, `redis` 8.4-alpine, `certbot/dns-cloudflare`, `python` 3.15-slim, `node` 26-alpine, `oven/bun`, `postgres:18-alpine` for the backup sidecar                                                                                                                          |
| root     | typos, taplo, prettier, gitleaks, trivy, syft, zizmor, actionlint                                                                                                                                                                                                                                                                                                                                                                                        |

Versions are read from the manifests, not from this file; this file names the tools, the manifests name the numbers.

## Local services

PostgreSQL, Redis and RabbitMQ run on the developer machine as native services bound to localhost, never as containers for development. The api reads them through `DB_*`, `CACHE_URL`, `QUEUE_URL` and `EVENT_URL`.

- PostgreSQL 18: role `ragx` / `ragx` owning databases `ragx` (development) and `ragx_test` (tests). The tests apply the migrations on boot and reset by dropping the lifecycle tables when the schema DSL changes.
- Redis 8 on `127.0.0.1:6379`; the tests use database `15`.
- RabbitMQ 4 on `127.0.0.1:5672` with `guest/guest` for development only; the tests declare and purge their own queues.

Each part owns its environment files (`.env`, `.env.<mode>`, `.secret*`), all ignored by git, each with a committed `.env.example`. The api loads `.env`, then `.env.<mode>`, then `.secret` layers, with the real process environment always winning.

## Gates

| Part     | Gate (run from the part's folder; every command must exit 0)                                                                                                                                                                                                                                                                                                                                                                          |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api/`   | `uv sync --locked --python 3.15` · `uv run ruff check` · `uv run mypy` · `uv run pytest` · `uv run python -m bootstrap check`                                                                                                                                                                                                                                                                                                         |
| `web/`   | `bun install --frozen-lockfile` · `bun run check` · `bun run typecheck` · `bun test` · `bun run build` (`bun run gate` chains them)                                                                                                                                                                                                                                                                                                   |
| `infra/` | `bash src/main.sh test --check` (bash -n, shellcheck, payload integrity, the literals law, every bash test including `docker compose config` and a real `nginx -t`)                                                                                                                                                                                                                                                                   |
| root     | `typos --config .typos.toml` · `taplo fmt --check && taplo lint` · `bunx prettier@<pinned> --config .prettierrc.yml --ignore-path .gitignore --no-error-on-unmatched-pattern --check "**/*.{md,mdx,yml,yaml,json,jsonc}"` · `gitleaks dir . --config .gitleaks.toml` · `trivy fs . --config .trivy.yml --exit-code 1` · `zizmor --offline --persona pedantic --config .zizmor.yml .github/workflows/` · `actionlint` on each workflow |

Benches are run on demand, never in CI: `api` `uv run python -m benches.bench_<name>`; `web` `bun run bench`. They fail on any unexpected status or a blown p99 budget.

## CI and release

- `.github/workflows/global.yml` runs the root scanners and a final `gate` job; `api.yml`, `web.yml` and `infra.yml` run the part gates (the infra workflow also builds the api image and one web image). Every part workflow has `workflow_call` and `paths` filters, so a change runs exactly the gates it can break.
- `release.yml` runs on a `v*` tag: it requires a semver tag on `main` and a `## vX.Y.Z` section in `CHANGELOG.md`, calls every gate, then publishes a GitHub release with the changelog section as notes. A `-suffix` tag is a prerelease. No binaries are attached; the infra bundle is built by its forge on demand.
- CI checks, typechecks, tests and builds. It never starts an application, runs a browser flow or measures runtime performance. Browser flows are manual tools; benches are local.

## The platform in production

The infra renders and runs the whole platform from one bundle on one box: nginx (TLS 1.2/1.3, HTTP/2 and HTTP/3, HSTS, per-client rate limits, an edge cache), the api with a worker and a scheduler, one container per web spec, PostgreSQL 18, RabbitMQ 4 and Redis 8 on an internal network, a backup sidecar, certbot, systemd units for boot, backups and renewals. Images are built from `infra/src/template/docker/` and published to a registry under the repository path, tagged with the git sha. `infra.md` carries the laws and the release line.

## Traps

- A build of the api image needs a uv image the registry can pull anonymously; on a machine where the default registry refuses anonymous pulls, pass `--build-arg UV_IMAGE=astral/uv:<version>`. A sandboxed docker build without DNS needs `--network=host` (the infra knob `DOCKER_NETWORK`).
- The api's default browser origins are `localhost` only, so a panel is opened on `http://localhost:3000`; on `http://127.0.0.1:3000` every api call fails CORS preflight.
- Only content-hashed static files (`_next/static/`, the api's stamped assets) may be served `immutable`.
- Ports 80 and 443 are often taken on a developer machine; the infra lab binds `HTTP_PORT=18080 HTTPS_PORT=18443 BIND_ADDRESS=127.0.0.1`.
- Docker compose: single-quoted env-file values are literal; double-quoted and bare values interpolate `$`. A compose `secrets: file:` bind mount keeps the host file's mode (a `0600` host file is unreadable by a non-root container user); an `environment:` secret cannot be used with `read_only: true`.
- Bash: `VAR=x source file; fn` does not keep `VAR` for `fn`; use `env VAR=x bash -c "source file; fn"`.
- A local `actionlint` may reject `$/.github/workflows/x.yml`, GitHub's same-commit syntax for reusable workflows; zizmor accepts it. Lint the other workflows one by one.
