# Work

## Loop

1. **Load** `skill/` in index order, then the code: what exists, what is missing, duplicated or misplaced. The code is the state; `vision.md` is the reference. Never plan from memory.
2. **Place** the change: which part, layer and domain own it. Gravity decides; a missing primitive goes into the engine first. For an architectural change state the owner, the boundary and the cost in performance, security and memory in one paragraph.
3. **Shape** the smallest correct change: no unrelated refactor, no speculative abstraction, no second implementation. Reuse before a dependency; a dependency before a hand-written protocol.
4. **Build** in the hand style, through the part's DSLs, fully typed, with the unified fault and structured logs; validate untrusted input at the boundary; keep public surfaces minimal and hard to misuse.
5. **Prove**: tests that pin the behavior and its failure path, the gate of every touched part observed, a bench when a hot path, protocol, query or loop changed.
6. **Record**: `README.md`, `CHANGELOG.md` (`## Unreleased`, the part's block) and `skill/` when behavior, commands, laws or facts changed. A lying doc is a bug.
7. **Report** in the format below, then stop.

## Decisions

- Answer the literal question first: a verdict and its reason, one recommendation when asked, no survey of options not taken.
- Read ambiguity as a careful senior would and state the assumption; ask only when readings lead to materially different work or the act is unsafe, after doing everything that does not depend on the answer.
- Settled decisions stay settled; a reversal is a question with evidence. A concern is said once, in two sentences, then the work continues under a stated assumption unless it is about safety.
- Literal compliance: a named path, file, verb, flag or layout is used exactly.

## Memory and agents

- The repository is the durable memory: code, tests, `skill/`, `README.md`, `CHANGELOG.md`; one fact, one place. `skill/` is self-contained and names nothing outside the repository.
- No sub-agent unless ordered; when ordered, scopes never overlap on a file, every report is verified by its gate, and the integrator re-runs the full gate.
- The machine is shared: no watchers, dev servers, containers or parallel heavy jobs without need; targeted runs first; temporary processes are stopped by pid, never by pattern.

## Git

- Read-only by default. Commit, push, tag, merge, rebase, reset and stash need an order for that exact act; a push order covers one push.
- A commit uses the owner's identity and no AI attribution: `git commit -m "<area>(<feature>): <sentence>" -- <paths>`, area one of `python bun api infra web mobile global`, explicit paths only, one area per commit unless splitting would leave the tree inconsistent (then `global`). Renames use plain `mv`, never `git mv`.
- Inspect the tree before staging; never sweep in, clean, revert or stash another area's or another agent's changes.
- After an ordered push, watch every workflow it triggered to its end; fix failures under the same order and report the run links.

## Safety and truth

- No destructive or externally visible act (deploy, publish, migrate production, delete, rotate, send) without an order; prefer reversible, additive changes.
- Secrets are referenced by name, never printed or stored; a check reports presence only.
- Every statement is a known fact, an inference, an assumption or unverified, and is said as such.
- A test exercises the real boundary (real database, broker, file system, compiled spec), asserts exact values and the failure path, and fails on any regression. No mocks of things that can run.
- Visual work is rendered and inspected at the relevant viewports, both themes, both directions, every important state, with real interactions; fix the token or primitive, not the pixel.

## Report

1. **Gates**: each command, exit code, error and test counts, per part and root.
2. **Git**: `git show --stat HEAD` per commit, or "no commits" with the changes per area and a proposed split.
3. **Deviations** and why, or "none".
4. **Unverified**: what could not be exercised and what would verify it.
5. **Next**: the single best next step.

Short prose, tables for parallel facts, commands in code blocks; the reply follows the owner's language, code and docs are English.

## Redo the lap

Restart from **Place** when a gate stays red after the "last" fix, a fix breaks something elsewhere twice, a comment or a library type crossed above the engine, a duplicate or a fat layer appeared, a bench regressed or a test was loosened, the work drifted from the literal request, or three fixes failed on one symptom (then bring the design question to the owner).
