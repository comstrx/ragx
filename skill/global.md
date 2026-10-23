# Global

The root owns what every part obeys: scanners, ignore files, editor and format contracts, documents, changelog, commit grammar, labels, owners and the workflows. A part never duplicates a root rule; a root rule never carries a part's business.

## Root

```
ragx/
├── .github/        workflows, dependabot, labeler, labels, CODEOWNERS, issue and PR templates
├── .editorconfig   4 spaces, 2 for yaml/json/md, lf, final newline, trimmed whitespace (md keeps trailing)
├── .gitignore      every ecosystem's artifacts, env and secret files, keys, caches, build outputs
├── .dockerignore   the same list, so no context carries an env file, a cache or node_modules
├── .gitattributes  line endings and binary marks
├── .prettierrc.yml Markdown, YAML, JSON (120 columns, 2 spaces, single quotes in YAML, prose preserved)
├── .taplo.toml  .typos.toml  .gitleaks.toml  .trivy.yml  .syft.yml  .zizmor.yml
├── README.md  CHANGELOG.md  CONTRIBUTING.md  SECURITY.md  SUPPORT.md  CODE_OF_CONDUCT.md  LICENSE (Apache 2.0)
├── AGENTS.md       the pointer to skill/
├── skill/          the contract
├── engine/         python/ bun/
└── product/        api/ infra/ web/ mobile/
```

## Laws

- **One exclusion list**: the same directories in the same order in `.trivy.yml`, `.syft.yml`, `.taplo.toml`, `.typos.toml`, and as path regexes in `.gitleaks.toml`; a new artifact directory joins all five in one change.
- **No standing exceptions**: no scanner ignore file until a real finding must be accepted; then `.trivyignore.yaml` names the id, the paths and a testable statement, and dies with its last entry. No inline scanner knobs.
- **Scoped formatting**: Prettier formats `md mdx yml yaml json jsonc`, taplo formats TOML, `.gitignore` is the only ignore list they read; their output is accepted as is. Everything else is the hand style.
- **Spelling is a gate**: a true word typos rejects joins `[default.extend-words]`, never a per-file silence.
- **Secrets never enter the tree**: parts read ignored `.env*`/`.secret*`; examples carry names and neutral defaults; gitleaks scans the tree and the history; an allowlist names the exact path and the reason.
- **Supply chain**: every action hash-pinned with its version comment and allowlisted in `.zizmor.yml`; every workflow image pinned by digest; every dependency locked and updated by Dependabot weekly (7-day cooldown, one group per ecosystem, label `deps`, prefix `<area>(deps)`).
- **Docs tell the truth**: the README names the current parts, gates, measured numbers (date and machine) and commands; a change that alters any of them updates it in the same lap.

## Changelog and commits

- `CHANGELOG.md` opens with `## Unreleased`, one `### <area>` block per touched area (`global python bun api infra web mobile`), past-tense facts about behavior. A release moves it under `## vX.Y.Z — YYYY-MM-DD`; the release workflow refuses a tag without its section and publishes it as the notes.
- Commits: `<area>(<feature>): <sentence>`, lowercase present-tense fact, no AI attribution, explicit paths, one area per commit (`global` only for an atomic cross-area change). Labels mirror the areas plus `ci deps docs security bug enhancement`; `CODEOWNERS` is `* @comstrx`.

## Workflows

| Workflow                     | Runs on                                                             | Does                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| ---------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `global.yml`                 | push to `main`, every PR, dispatch, call                            | gitleaks (history), trivy, syft (artifact), zizmor (pedantic), typos, taplo + Prettier, then a `gate` that fails on any failure or cancel                                                                                                                                                                                                                                                                                                      |
| `python.yml`                 | `engine/python/**`                                                  | Postgres (pgvector), RabbitMQ, Redis by digest; `uv sync --locked`, ruff, mypy, pytest (the stage provisions `engine_test`)                                                                                                                                                                                                                                                                                                                    |
| `bun.yml`                    | `engine/bun/**`                                                     | install, check, lint, test, audit                                                                                                                                                                                                                                                                                                                                                                                                              |
| `api.yml`                    | `product/api/**`, `engine/python/**`                                | the same services; sync, `bootstrap provision`, ruff, mypy, pytest, `bootstrap check`                                                                                                                                                                                                                                                                                                                                                          |
| `web.yml`                    | `product/web/**`, `engine/bun/**`                                   | Node 26, engine installed and linked, install, check, typecheck, test, `deliver --all` (build and audit every spec)                                                                                                                                                                                                                                                                                                                            |
| `mobile.yml`                 | `product/mobile/**`, `engine/bun/**`                                | Node 26, engine installed and linked, install, check, typecheck, test, `export --all` (Hermes per spec)                                                                                                                                                                                                                                                                                                                                        |
| `infra.yml`                  | `product/infra/**`, `product/api/**`, `product/web/**`, `engine/**` | Linux and macOS offline gate and release bundle; one image per part (the matrix lists them) built and trivy-scanned; publication only by manual dispatch                                                                                                                                                                                                                                                                                       |
| `release.yml`                | a `v*` tag                                                          | `plan` (semver, on `main`, changelog section) → every gate above through `$/.github/workflows/<file>.yml` → GitHub release → `deploy` when `DEPLOY_AUTO` (only after the release published)                                                                                                                                                                                                                                                    |
| `deploy.yml`                 | dispatch from `main` or the release                                 | `plan` (actor in `DEPLOY_ACTORS`, tag on `main`) → `images` (a matrix job per part, no SSH key; built per baked address, scanned, pushed once) → `mode` (GitOps or SSH; digests pinned by `infra image resolve` with read-only packages) → `publish` (GitOps only: `infra publish`, the one job with `contents: write`, no SSH secret) or `deploy` (SSH, read-only: `infra deploy`, `rollback`, `backup`, `restore`) → `notify` on any failure |
| `labeler.yml` · `labels.yml` | PRs · label changes                                                 | path labels, skipped for pull requests from forks, whose token cannot write · label sync                                                                                                                                                                                                                                                                                                                                                       |

- Shared shape: per-workflow `concurrency` with `cancel-in-progress` (the release keeps it off); `permissions: contents: read` with a job-level widening only where a job writes; `defaults.run` in the part's folder; `timeout-minutes` on every job; `persist-credentials: false` on every checkout; no publication secret in a verification job.
- A part workflow runs when its part, its engine or itself changes and exposes `workflow_call`, so the release composes gates and never duplicates them. CI checks, typechecks, tests and builds; it never starts an app, runs a browser flow or measures performance.
- A step calls a command that exists in the part's manifest or entry, never a bespoke script. A new action joins the zizmor allowlist after its source, maintainer and permissions were read; a new service is pinned by digest with a `health-cmd`; a new workflow takes the shared shape, a `paths` filter, `workflow_call` and a row above.
- Image publication: CI builds and scans without pushing; only a manual Infra dispatch with `publish=true` on `main` pushes (GHCR via `GITHUB_TOKEN`, Docker Hub via a dedicated push token). No workflow writes desired state or tags to Git.

## Root gate

Before any push that touches the root or `.github/`, in this order:

```bash
typos --config .typos.toml
taplo fmt --check && taplo lint
bunx prettier@<pinned> --config .prettierrc.yml --ignore-path .gitignore --no-error-on-unmatched-pattern --check "**/*.{md,mdx,yml,yaml,json,jsonc}"
gitleaks dir . --no-banner --redact --config .gitleaks.toml
trivy fs . --config .trivy.yml --exit-code 1
syft scan dir:. --config .syft.yml --source-name ragx
zizmor --offline --persona pedantic --config .zizmor.yml .github/workflows/
actionlint .github/workflows/<file>.yml
```

The pinned Prettier and taplo versions are the ones `global.yml` names; a local actionlint may reject the `$/` reusable-workflow syntax the release uses (zizmor accepts it). A local `gitleaks dir` and `trivy fs` also read ignored local files such as a filled `.env.local`; CI scans a clean checkout.

## When CI is red

Read the failing job to its first error; reproduce with the step's exact command; fix the cause in the part, never by loosening a gate; run the part's full gate; push only under the order's scope and watch every triggered run to green. An external failure (registry, index, runner) is re-run once after its cause is read; a second failure is reported.
