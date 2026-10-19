# GitHub

`.github/` holds the workflows, Dependabot, the labeler, the labels, the owners and the templates. CI checks, typechecks, tests and builds; it never starts an application, runs a browser flow or measures runtime performance.

## Workflows

| Workflow      | Triggers                                                     | Jobs                                                                                                                                                                                                                                                     |
| ------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `global.yml`  | push to `main`, every pull request, dispatch, call           | `leaks` (gitleaks over the full history), `vulns` (trivy, `--exit-code 1`), `sbom` (syft, uploaded as an artifact), `actions` (zizmor pedantic), `spelling` (typos), `formatting` (taplo + Prettier), then `gate` (fails on any failure or cancellation) |
| `api.yml`     | `api/**` and the workflow itself; dispatch, call             | `verify`: services `postgres:18`, `rabbitmq:4.2-alpine`, `redis:8.4-alpine` pinned by digest with health commands; `uv sync --locked --python 3.15`, `ruff check`, `mypy`, `pytest`, `python -m bootstrap check`                                         |
| `web.yml`     | `web/**` and the workflow itself; dispatch, call             | `verify`: Bun from `web/package.json`, Node 26, `bun install --frozen-lockfile`, `bun run check`, `bun run typecheck`, `bun test`, `bun run build`                                                                                                       |
| `infra.yml`   | `infra/**`, `api/**`, `web/**`, its workflow; dispatch, call | Linux/macOS offline checks and release bundles; API/admin/client image build and scan; explicit manual publication only                                                                                                                                  |
| `release.yml` | push of a `v*` tag                                           | `plan` (semver tag, on `main`, a `## vX.Y.Z` section in `CHANGELOG.md` becomes the notes, `-suffix` marks a prerelease) → `global`, `api`, `infra`, `web` through `$/.github/workflows/<file>.yml` → `publish` (`gh release create --verify-tag`)        |
| `labeler.yml` | pull requests                                                | applies labels from `.github/labeler.yml` paths                                                                                                                                                                                                          |
| `labels.yml`  | changes to `.github/labels.yml`                              | syncs the label set                                                                                                                                                                                                                                      |

Shared shape of every workflow: `concurrency` per workflow and ref with `cancel-in-progress: true` (the release keeps `false`), `permissions: contents: read` at the top and a job-level widening only where a job writes (release publication or the manual infra image-publication job), `defaults.run.shell: bash` with the part as `working-directory`, `timeout-minutes` on every job, `persist-credentials: false` on every checkout, no publication secrets in verification jobs; the explicit Docker Hub publication path uses its dedicated push credentials.

## Pinning and audit

- Every `uses:` is pinned to a full commit sha with the version as a trailing comment (`actions/checkout@<sha> # v7.0.1`); every service image is pinned by digest with the tag as a comment. A floating tag is refused by zizmor (`unpinned-uses: hash-pin`) and by review.
- Every action is listed in `.zizmor.yml` `forbidden-uses.allow`; a new action joins the allowlist in the same change, after its source, maintainer and permissions were read.
- Before a push that touches `.github/`: `zizmor --offline --persona pedantic --config .zizmor.yml .github/workflows/` and `actionlint <file>` per workflow (a local actionlint may reject the `$/` reusable-workflow syntax the release uses; zizmor accepts it). Prettier formats the YAML.
- Dependabot (`.github/dependabot.yml`): `github-actions` at the root, `uv` under `/api`, `docker` under `/infra/src/template/image`, `bun` under `/web`; weekly on Monday, a 7-day cooldown, one group per ecosystem, label `deps`, commit prefix `<area>(deps)`. Image versions and digests live in `infra/Bash.toml`.

## Paths and composition

- A part workflow runs only when its part or its own file changed; the infra workflow also watches the api and web manifests and lockfiles because its images build from them. A change that could break a gate the filter would skip triggers it by hand (`workflow_dispatch`) or is pushed with the file that owns the filter.
- Every part workflow exposes `workflow_call` so the release composes them; the release never duplicates a gate.
- Runner images are `ubuntu-latest`; a tool the gate needs is installed by a pinned setup action (uv, Bun, Node, trivy, syft, zizmor, typos, binstall for taplo); dependency vulnerabilities are trivy's job over the lockfiles plus Dependabot alerts, so no dependency-review job exists or by the part itself (the infra bundle installs shellcheck, jq and the rest through `tool ensure`).

## Adding or changing

- **A step**: inside the part's `verify` job, calling a command that exists in the part's manifest (`package.json` scripts, `pyproject.toml` tools, the forge verbs); never a bespoke script in the workflow file.
- **A service**: pinned by digest, with a `health-cmd`, the env the part expects (`DB_*`, broker urls), and the part's tests exercising it for real.
- **A workflow**: the shared shape above, a `paths` filter, `workflow_call`, hash-pinned actions in the allowlist, a row in the table above and a line in `stack.md`.
- **Image publication**: ordinary CI builds and scans without pushing. Only a manual Infra dispatch with `publish=true` on `main` enables publication; GHCR uses `GITHUB_TOKEN`, Docker Hub uses a dedicated push token. Server pull credentials are separate. No workflow writes desired state or release tags to Git.

## When CI is red

1. Read the failing job's log to the first error; reproduce it locally with the exact command the step runs.
2. Fix the cause in the part, never by loosening the gate (no skipped test, no lowered severity, no new exception without a statement).
3. Run the part's full gate locally, then push only under the scope of the order that triggered the work, and watch the runs until every workflow the push triggered is green.
4. A failure caused by an external service (a registry, a package index, a runner outage) is re-run once after the cause is read; a second failure is reported, not retried blindly.
5. The report names the run links, what failed, what fixed it and what was unverified.

## Templates and owners

- `PULL_REQUEST_TEMPLATE.md`: scope, what and why, a checklist (one area, local gates, tests and benches updated, no secrets, commit grammar), rollback.
- `ISSUE_TEMPLATE/`: `bug_report.yml`, `feature_request.yml`, `config.yml` routing questions to Discussions and security reports to private advisories.
- `CODEOWNERS`: `* @comstrx`. `labels.yml` defines `api infra web global ci deps docs security`; `labeler.yml` maps paths to them (`deps` from manifests, lockfiles, Dockerfiles and `infra/.env.example`; `security` from the scanner configs and `SECURITY.md`).
