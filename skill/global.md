# Global

The repository root owns the governance every part obeys: the scanner configurations, the ignore files, the editor contract, the documents, the changelog, the commit grammar, the labels and the owners. A part never duplicates a root rule; a root rule never carries a part's business.

## The root tree

```
ragx/
├── .github/            workflows, Dependabot, labeler, labels, CODEOWNERS, issue and pull request templates   (see github.md)
├── .editorconfig       4 spaces everywhere, 2 for yaml/json/md, lf, final newline, trimmed whitespace (md keeps trailing)
├── .gitignore          every ecosystem's artifacts (Python, Bun/Node/Next, Rust, PHP, mobile), env and secret files, keys, caches, build outputs
├── .dockerignore       the same list, so an image context never carries an env file, a cache or a node_modules
├── .gitattributes      line endings and binary marks
├── .prettierrc.yml     Markdown, YAML, JSON formatting (120 columns, 2 spaces, single quotes in YAML, prose preserved)
├── .taplo.toml         TOML formatting and lint (4 spaces, 100 columns)
├── .typos.toml         spelling with the one exclusion list and a short allowlist of true words
├── .gitleaks.toml      secret detection with the one exclusion list as regexes and reasoned allowlists
├── .trivy.yml          vulnerabilities, misconfigurations, secrets and licenses over the tree
├── .syft.yml           the SBOM configuration
├── .zizmor.yml         workflow audit: hash-pinned uses only, an explicit allowlist of actions
├── README.md           the product, the three parts and their gates, engineering, measured performance, security, development
├── CHANGELOG.md        one section per release, one block per part
├── CONTRIBUTING.md  SECURITY.md  SUPPORT.md  CODE_OF_CONDUCT.md  LICENSE (Apache 2.0)
├── AGENTS.md           the pointer to skill/
└── skill/              this folder
```

## Laws

- **One exclusion list.** The same directories in the same order in `.trivy.yml`, `.syft.yml`, `.taplo.toml`, `.typos.toml`; `.gitleaks.toml` carries the same set as path regexes. A new artifact directory is added to all five in one change. Each file's own rules come after the list.
- **No standing exceptions.** No ignore file exists for a scanner until a real finding must be accepted; then `.trivyignore.yaml` is created with the id, the exact paths and a statement a reviewer can test, named in `.trivy.yml` through `ignorefile:`, and deleted again when its last entry goes. No `# trivy:ignore` inline knobs. A file that only says "nothing is ignored" is noise and is removed.
- **Formatting is scoped.** Prettier formats `md mdx yml yaml json jsonc` (never code), the compose template included: placeholders are plain scalars; taplo formats TOML. `.gitignore` is the only ignore list they read. Their output is accepted as is; the hand style governs everything else (`style.md`).
- **Spelling is a gate.** `typos` runs over the tree; a legitimate word the dictionary rejects is added to `[default.extend-words]` with its correct spelling, never silenced per file.
- **Secrets never enter the tree.** Parts read ignored `.env*` and `.secret*` files; the committed examples carry names and neutral defaults only; the infra renders secrets into private files on the box. `gitleaks` runs over the working tree and the history; an allowlist entry names the exact path pattern and the reason.
- **Supply chain.** Every GitHub action is hash-pinned with its version in a comment and listed in the zizmor allowlist; every container image in a workflow is pinned by digest with its tag in a comment; dependencies are locked (`uv.lock`, `bun.lock`) and updated by Dependabot weekly with a cooldown, grouped per ecosystem, labeled `deps`, prefixed `<area>(deps)`.
- **Docs tell the truth.** `README.md` describes the current parts, gates, measured numbers (with the date and the machine) and the development commands; a change that alters any of them updates the README in the same lap.

## Changelog

`CHANGELOG.md` opens with `## Unreleased` holding one `### <part>` block per touched part (`api`, `web`, `infra`, `global`), each a list of past-tense facts about behavior, never about files. A release moves the block under `## vX.Y.Z — YYYY-MM-DD`; the release workflow refuses a tag whose section is missing and uses the section as the release notes. A lap that changes behavior adds its lines before it reports.

## Commits and areas

- `<area>(<feature>): <sentence>` with the area one of `api infra web global`; the sentence is a lowercase, present-tense fact; no AI attribution of any kind.
- One area per commit; a genuinely atomic cross-part feature uses `global`. Paths are staged explicitly (`git commit -m "…" -- <paths>`); the working tree is inspected first so nothing foreign is swept in.
- Labels mirror the areas (`api infra web global`) plus `ci deps docs security`, applied by the labeler from paths. `CODEOWNERS` names the owner of everything.

## Root gate

Run from the repository root before any push, in this order, every command exiting 0:

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

The pinned Prettier version is the one `.github/workflows/global.yml` names; the same holds for taplo. A new scanner joins the workflow, this list and `stack.md` in one change.

## What belongs where

| Belongs to the root                                                          | Belongs to a part                                                                                                                              |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Scanner configs, ignore files, editor contract, formatting configs           | Lint and type configs of the part's language (`pyproject.toml`, `biome.json`, `tsconfig.json`, the forge's shellcheck knobs in `.env.example`) |
| Workflows, Dependabot, labels, owners, templates                             | The commands a workflow runs (they live in the part's manifest or entry)                                                                       |
| README, CHANGELOG, CONTRIBUTING, SECURITY, SUPPORT, CODE_OF_CONDUCT, LICENSE | The part's `.env.example`, `.secret.example`, templates, tests, benches                                                                        |
| `skill/` and `AGENTS.md`                                                     | Nothing: a part never carries an agent instruction file of its own                                                                             |
