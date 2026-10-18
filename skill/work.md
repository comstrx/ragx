# Work

## The loop

1. **Load.** Read `skill/` in the order `index.md` gives, then the code of the area: what exists, what is missing, what is duplicated, what sits in the wrong layer. The code is the truth about the current state; `vision.md` is the reference for every decision. Never plan from memory of a previous session.
2. **Place.** Decide who owns the change (which part, which layer, which domain) before writing anything. Apply gravity: the lowest layer able to carry the logic owns it; a missing primitive is added to the core first, tested there, then consumed. State the ownership, the dependency boundary and the impact on performance, security and memory in one short paragraph when the change is architectural.
3. **Shape.** The smallest correct change. No unrelated refactor, no speculative abstraction, no second implementation of something that exists. Reuse before adding a dependency; add a dependency before writing a protocol by hand.
4. **Build.** Write to the hand style, through the DSLs of the part, with full types, the unified fault and structured logs. Validate untrusted input at the boundary. Keep public surfaces minimal and hard to misuse.
5. **Prove.** Add or change the tests that pin the behavior and its failure path. Run the gate of every touched part and observe the output. Measure with a bench when the change touches a hot path, a protocol, a query or a loop.
6. **Record.** Update `README.md`, `CHANGELOG.md` (the `Unreleased` block of the part) and the relevant `skill/` file when behavior, commands, laws or facts changed. A doc that lies is a bug.
7. **Report.** In the fixed format below. Then stop; do not start the next task without an order.

## Intake and decisions

- Answer the literal question first. A verdict plus its reason; no flattery, no fence-sitting, no survey of options the agent will not take. When a recommendation is asked, give one.
- Interpret ambiguity the way a careful senior colleague would and state the assumption; ask only when different readings lead to materially different work or when an action is unsafe. Do everything that does not depend on the answer before asking.
- A settled decision (in `vision.md`, in the part files, or stated by the owner in the conversation) stays settled. A reversal is a question carried with evidence, never an action.
- A concern about the request is said once, in two sentences, and the work continues under a stated assumption unless the concern is safety.
- Literal compliance: when the owner names a path, a file, a verb, a flag or a layout, that exact name is used; "equivalent" is not compliance.

## Memory

- The repository is the only durable memory: code, tests, `skill/`, `README.md`, `CHANGELOG.md`. A fact worth keeping across sessions is written into the file that owns it (one fact, one place, the existing file extended before a new one is created), never into a side note the next agent cannot find.
- Session memory is a short ledger of the owner's decisions and the current state of the lap (what passed, what is unverified, what is pending), kept terse and re-derived from the transcript after any context compaction before acting again. Anything learned about the machine or the environment that is not a project fact stays out of the repository.
- `skill/` is self-contained: it never references a path, a tool account, a private document or a source outside this repository. When an external source inspires a design, the design is restated here in the project's own terms.

## Sub-agents and parallel work

- No sub-agent is spawned unless the owner orders it. The default is to do the task directly with the minimum number of processes and the smallest context.
- When parallel agents are authorized: each gets a brief naming the goal, the files it may touch, what is already ruled out and the gate it must pass; scopes never overlap on a file; nothing an agent reports is trusted until its gate output is read; the integrating agent runs the full gate again.
- Machine economy at all times: other agents and developer processes may share the machine. No watchers, dev servers, containers, duplicate builds or parallel heavy jobs without need; targeted tests and builds before repository-wide ones; temporary processes are stopped by pid (never by pattern) when their job is done; nothing is rebuilt that did not change.

## Git

- Git is read-only by default: inspect status, diff, log, blame and history freely.
- No commit, push, tag, merge, rebase, reset or stash without an explicit order, and an order covers exactly the action it names (a push order is one push of what was named, nothing more).
- A commit, when ordered, uses the owner's existing git identity, never an AI author, co-author or attribution line, with the message `<area>(<feature>): <sentence>` where the area is one of `api infra web global`, and stages explicit paths only: `git commit -m "…" -- <paths>`. One area per commit unless a single atomic feature spans areas and splitting would leave the repository inconsistent (then the area is `global`).
- Before staging, the working tree is inspected and the agent's changes are separated from unrelated existing changes; nothing of another area or another agent is swept in; unrelated changes are never cleaned, reverted or stashed.
- After an ordered push, the workflows it triggers are watched until they conclude, failures are fixed and pushed again only under the same order's scope, and the final verdict is reported with the run links.

## Safety and secrets

- No destructive or externally visible action (deploy, publish, migrate production data, delete, apply infrastructure, rotate credentials, send a message, modify a live system) without an explicit order; reversible, additive changes with a clear rollback path are preferred everywhere.
- Secrets, credentials and private data are never printed, logged, copied, rendered world-readable or committed; code references names, never values; a check that needs a value reads it where it lives and reports only presence.
- Before a state-changing command, the evidence must support that exact command; a symptom that pattern-matches a known failure may have a different cause.

## Verification and truth

- Nothing is claimed that was not observed. Every statement is one of: known fact (observed), inference (from observed facts, said so), assumption (stated as such), unverified (said so, with what would verify it).
- A test is brutal: it exercises the real boundary (the real test database, the real broker, the real file system, the real compiled spec), asserts exact values and the failure path, and would fail on any regression of the behavior it pins. Few, flat files; no mocks of things that can be run; no test that passes without exercising code.
- A bench is a law: it runs a representative workload against the real stack, reports p50/p95/p99, throughput and the environment, and fails on any unexpected status or a blown p99 budget. A performance claim without a bench run is an opinion and is reported as unverified.
- Visual work is rendered and inspected: the affected surface at the relevant viewports, both themes, both directions when applicable, every important state (loading, empty, partial, error, offline, validation, permission, success, destructive confirmation, long and short content), with real interactions, not screenshots alone. Fix the system (token, primitive, layout rule), not the pixel.

## Reporting format

Every report, in this order and nothing before it:

1. **Gates**: each command, its exit code and its error count (and test counts), per touched part and for the root.
2. **Git**: `git show --stat HEAD` for every commit made; "no commits" otherwise, with a one-line list of the uncommitted changes per area and a proposed commit split.
3. **Deviations** from the instructions and why, or "none".
4. **Unverified**: anything that could not be exercised (needs a live box, a provider key, a browser), said explicitly.
5. **Next**: the single best improvement or the fix for an open problem.

Short prose, tables for parallel facts, commands in code blocks, no closing summary. The reply language follows the owner; code, docs and commit messages are English.

## When it is done

`index.md` defines done. Three additional stop conditions: the owner's literal request is fully satisfied (not narrowed, not widened, not transformed); every part of the scope that turned out blocked is named with the reason, while every other part was finished in full; nothing in the report is a promise about future work.

## When the lap is redone

A lap restarts from **Place** (not from the last edit) when any of these appears:

- A gate is red after the "last" fix, or a fix for one failure revealed a failure in another place twice in a row.
- The change needed a comment to be understood, or a third-party type, a standard-library type or a protocol detail crossed above the core.
- A duplicate of an existing capability was written, or a layer above the core grew beyond a thin pipeline (a loop, a retry, a parser, a provider call, a format).
- A bench regressed beyond its budget, or a test had to be loosened to pass.
- The implementation drifted from the literal request, or an assumption turned out wrong after the owner answered.
- Three fixes failed on the same symptom: stop, question the design, and bring the question to the owner with the evidence instead of a fourth fix.
