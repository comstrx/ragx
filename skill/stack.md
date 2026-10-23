# Stack

## Policy

- The newest stable release of every runtime, library, image and action on the day of the task, checked at the official source. Manifests (`pyproject.toml`, `uv.lock`, `package.json`, `bun.lock`, `product/infra/Bash.toml`, workflow pins) name the numbers; this file names the tools.
- Mature libraries with native cores over custom code; custom code needs a measured advantage. A library that fails on the pinned runtime is replaced after it was installed and exercised there, never on hearsay.
- One strict type checker and one linter with every rule on per language; no formatter for Python or TypeScript (the hand style is the format); Prettier for Markdown/YAML/JSON, taplo for TOML.

## Parts

| Part             | Runtime and tools                                                                                                                                                                                                                                                                                                                                                    |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `engine/python`  | CPython 3.15 (GIL build; free-threaded only as a measured experiment), uv workspace, hatchling, FastAPI, Granian, SQLAlchemy Core + asyncpg, pydantic, PyJWT, cryptography, argon2-cffi, Jinja2, httpx, orjson, structlog, obstore, aio-pika, redis, kreuzberg, pypdfium2, pypdf, python-calamine, Pillow, PyAV; ruff (`ALL`), mypy strict + pydantic plugin, pytest |
| `engine/bun`     | Bun (manager, tests, tooling runtime), zod 4, zustand 5, lucide-static, subset-font, mitata, React as a peer; Biome (lint), TypeScript strict                                                                                                                                                                                                                        |
| `product/api`    | engine/python by path; ruff, mypy, pytest, watchfiles                                                                                                                                                                                                                                                                                                                |
| `product/web`    | engine/bun by link, Next 16, React 19, Node 26 (Next's build and standalone server), Bun (manager, tools, release server), Tailwind CSS 4 + PostCSS, Biome, TypeScript strict                                                                                                                                                                                        |
| `product/mobile` | engine/bun by link, Expo SDK with its bundled React Native and React (Expo's ranges are the truth), react-native-screens, Metro + Hermes, react-native-web for render tests, Biome, TypeScript strict                                                                                                                                                                |
| `product/infra`  | Bash 5.2+, ShellCheck (pinned), Docker Compose, HAProxy, Portainer CE, curl, SSH, checksummed tools; image digests in `Bash.toml`                                                                                                                                                                                                                                    |
| root             | typos, taplo, Prettier, gitleaks, trivy, syft, zizmor, actionlint                                                                                                                                                                                                                                                                                                    |

## Services

PostgreSQL 18 (pgvector), Redis 8 and RabbitMQ 4 run natively on localhost, never as development containers. Roles: `ragx` owns `ragx` and `ragx_test` (api); `engine` owns `engine_test`, which the engine's stage provisions itself through the local admin (`DB_ADMIN_*`). Redis tests use db 15; RabbitMQ tests declare and purge their own queues. Product parts own ignored env files plus a committed `.env.example`; engines read only what their tests need from the process.

## Gates

Run from the part's folder; every command exits 0.

| Part             | Gate                                                                                                            |
| ---------------- | --------------------------------------------------------------------------------------------------------------- |
| `engine/python`  | `uv sync --locked` · `uv run ruff check` · `uv run mypy` · `uv run pytest`                                      |
| `engine/bun`     | `bun install --frozen-lockfile && bun link` · `bun run check` · `bun run lint` · `bun test` · `bun audit`       |
| `product/api`    | `uv sync --locked` · `uv run ruff check` · `uv run mypy` · `uv run pytest` · `uv run python -m bootstrap check` |
| `product/web`    | `bun install --frozen-lockfile` · `bun run check` · `bun run typecheck` · `bun test` · `bun run deliver --all`  |
| `product/mobile` | `bun install --frozen-lockfile` · `bun run check` · `bun run typecheck` · `bun test` · `bun run export --all`   |
| `product/infra`  | `bash src/main.sh test --check` (offline; real Compose/HAProxy proofs run in bounded labs)                      |
| root             | the scanners in `global.md`                                                                                     |

Benches run on demand, never in CI: `uv run python -m benches.bench_<name>` (engine/python, product/api), `bun run bench` (engine/bun, web, mobile). They fail on an unexpected status or a blown p99; `BENCH_SCALE` widens budgets on a busy machine.

## Traps

- Docker builds need `--network=host` in a sandbox; where anonymous GHCR pulls fail, pass `--build-arg UV_IMAGE=astral/uv:<version>`.
- Browser origins default to `localhost`: open panels on `http://localhost:3000`, never `127.0.0.1`.
- Only content-hashed files (`_next/static/`, stamped assets) may be served `immutable`.
- Ports 80/443 are often taken locally: infra labs bind `HTTP_PORT=18080 HTTPS_PORT=18443 BIND_ADDRESS=127.0.0.1`.
- Compose env files: single quotes are literal, double quotes and bare values interpolate `$`; a `secrets: file:` mount keeps the host mode; an `environment:` secret cannot be read-only.
- Bash: `VAR=x source file; fn` does not keep `VAR` for `fn`; use `env VAR=x bash -c "source file; fn"`.
- `link:engine` needs `bun install && bun link` in `engine/bun` first (locally, in CI, in the web image).
- An image ignore file that re-includes a directory (`!dir/`) re-includes its `.venv` and `node_modules`; name files and globs only.
