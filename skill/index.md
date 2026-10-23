# Index

RagX is one monorepo, two layers, one governance. `engine/` holds the generic foundations, `product/` holds RagX. Every folder below them is an independent workspace with its own manifest, lockfile, tests and gate. This folder is the contract every agent and engineer loads before touching a file.

```
ragx/
├── skill/            this contract
├── engine/python     the server engine: uv workspace, one package per domain under the `engine` namespace
├── engine/bun        the TypeScript engine: one package `engine`, one subpath per member
├── product/api       the RagX application over engine/python
├── product/infra     the platform carrier: one Bash bundle
├── product/web       the browser surfaces over engine/bun (Next.js)
└── product/mobile    the phone surfaces over engine/bun (Expo)
```

## Read

| File        | Holds                                                  | When                                    |
| ----------- | ------------------------------------------------------ | --------------------------------------- |
| `vision.md` | the product, the doctrine, tenancy, AI design, phasing | always                                  |
| `stack.md`  | toolchains, services, gates, traps                     | always                                  |
| `work.md`   | the loop, decisions, git, economy, truth, reporting    | always                                  |
| `style.md`  | the hand style per language                            | before writing or reviewing a line      |
| `global.md` | root governance, scanners, docs, workflows, release    | touching the root or `.github/`         |
| `python.md` | engine/python                                          | engine/python, product/api              |
| `api.md`    | product/api                                            | product/api                             |
| `bun.md`    | engine/bun                                             | engine/bun, product/web, product/mobile |
| `web.md`    | product/web                                            | product/web                             |
| `mobile.md` | product/mobile                                         | product/mobile                          |
| `infra.md`  | product/infra                                          | product/infra, delivery                 |

Order: `vision → stack → work → style`, then the part, then its engine, then the code of the area: what exists, what is missing, what is duplicated, what sits in the wrong layer.

## Creed

- The strongest, cleanest, fastest code the author has produced, every time. Enterprise grade is the floor.
- Correctness, simplicity, security, measured performance, maintainability and developer experience are optimized together; none is traded without evidence.
- The newest stable release of every tool on the day of the task; manifests and lockfiles are the truth, nothing is downgraded silently.
- Every integration lives in an engine (or the infra core); the layers above are pipelines of one or two lines. A trick a leaf needs becomes an engine verb, tested there.
- A rule that no test, lint or workflow enforces is a wish. Comments are naming defects: zero comments everywhere.
- Nothing is claimed that was not observed.
- Truth order: the code and its law tests, then this folder, then habit. A law test is never weakened; a law may only become harsher.

## Non-negotiables

- Git is read-only; every write needs an order naming that action. No destructive or externally visible act without an order.
- No secret is printed, logged, copied, rendered world-readable or committed.
- No sub-agent unless ordered. No formatter on Python or TypeScript.
- No speculative abstraction, no fashionable rewrite, no second owner of a capability.

## Done

1. The behavior exists once, in the lowest layer able to carry it.
2. The gate of every touched part passes, observed (`stack.md` lists them); a change in an engine also passes the gates of the parts that consume it.
3. Tests pin the behavior and its failure path; a mutation of the fix fails them.
4. Hot paths carry bench numbers.
5. `README.md`, `CHANGELOG.md` and this folder say the new truth.
6. The report names commands, exit codes, counts, deviations and everything unverified.
