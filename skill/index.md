# Index

RagX is one monorepo with exactly three parts (`api/`, `infra/`, `web/`) under one root governance (`.github/`, the scanner configs, the docs). This folder is the brain that every agent loads before working: what the product is, what it runs on, how code is written, how work is done, and the laws of each part.

## Files

| File        | Carries                                                                                                                                                                  | Read when                                     |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------- |
| `index.md`  | This router, the creed, the non-negotiables, the definition of done                                                                                                      | Always, first                                 |
| `vision.md` | The product, the architecture doctrine (gravity, thin layers, a core that keeps training, one owner per responsibility), tenancy, provisioning, auth, phasing            | Always                                        |
| `stack.md`  | Toolchains and versions, local services, the gate of every part, CI and release mapping, root scanners, environment files, traps                                         | Always                                        |
| `style.md`  | The hand style per language (Python, TypeScript, Bash, CSS, YAML/TOML/Markdown), naming, sizes, the zero-comment law, what linters enforce and what the hand enforces    | Before writing or reviewing any line          |
| `work.md`   | The operating loop, decisions, memory, sub-agents, git, resource economy, reporting, when a task is done, when a lap is redone, truth, safety                            | Always                                        |
| `api.md`    | The Python platform: layers, import and typing laws, the 30 core domains and their DSLs, the envelope, bootstrap, tests, benches, how to add anything                    | Working under `api/`                          |
| `web.md`    | The Next.js engine on Bun: layering, the std library, specs, validator laws, rendering, styles, tooling, tests, images, how to add a feature, a screen, a spec           | Working under `web/`                          |
| `infra.md`  | The bash bundle that carries the whole platform onto a Linux box as a Docker Compose monolith: modules, config, render laws, topology, release line, tests, verification | Working under `infra/`                        |
| `global.md` | Root governance: the scanner configs and their one exclusion list, the docs, the changelog, commits, labels, owners, what belongs to the root and what to a part         | Touching anything at the repository root      |
| `github.md` | The workflows: every job, pinning, permissions, concurrency, paths, release, Dependabot, how to add or change a workflow, what to do when CI is red                      | Touching `.github/` or chasing a workflow run |

## Reading order

1. `index.md` → `vision.md` → `stack.md` → `work.md` → `style.md`.
2. The file of the part the task lives in. A cross-cutting task reads every part it touches plus `global.md`.
3. The code of the area, before any plan: what exists, what is missing, what is duplicated, what sits in the wrong layer.

## Creed

- The strongest, cleanest and fastest code the author has ever produced, in every part, every time. Enterprise grade is the floor, not the ceiling.
- Correctness, simplicity, security, measured performance, maintainability and developer experience are optimized together; none is traded for another without evidence.
- The newest stable release of every tool and library on the day of the task, used to its full current capability. The manifests and lockfiles are ground truth; nothing is downgraded silently.
- Boundaries are enforced by tests, lints and CI, never by prose alone. A rule that cannot be checked is a wish.
- Code reads by itself. A comment is a naming defect: rename or restructure until the comment is unnecessary. Zero comments in every part.
- Every network, file, process and third-party access lives in a core layer; the layers above are thin pipelines over it. A trick needed in a leaf becomes a verb in the core, tested, and the leaf stays one line.
- Nothing is claimed that was not observed: a gate that was not run is "not run", a behavior that was not exercised is "unverified".

## Non-negotiables

- Git is read-only. No commit, push, tag, merge, rebase, reset or stash without an explicit order for that exact action. A push order covers exactly one push.
- No destructive or externally visible action (deploy, publish, migrate production, delete, rotate, send) without an explicit order.
- No secret is printed, logged, copied, rendered world-readable or committed. Names are referenced, values are not.
- No sub-agent is created unless the user orders it.
- No code formatter touches Python or TypeScript. Prettier formats Markdown, YAML and JSON; taplo formats TOML; nothing else is reformatted by a machine.
- No speculative abstraction, no fashionable rewrite, no second implementation of a capability the core already owns.

## Definition of done

A change is done when all of the following hold, and only then is it reported as done:

1. The requested behavior exists, in the lowest layer able to carry it, with no duplicate elsewhere.
2. The gate of every touched part passes with zero errors, run locally, output observed: `api` ruff + mypy + pytest + `bootstrap check`; `web` check + typecheck + test + build; `infra` `bash src/main.sh test --check`; root scanners for any root file.
3. Tests were added or changed so the behavior is pinned, including the failure path, and they are brutal, few and flat.
4. Anything performance-sensitive was measured with a bench and the numbers are in the report.
5. Docs that describe the changed behavior (`README.md`, `CHANGELOG.md`, this folder) say the new truth.
6. The report names the commands, exit codes, error counts, deviations and everything left unverified.

If one item fails, the lap is not finished: fix, re-run, re-report. `work.md` says when a lap is redone from the start.
