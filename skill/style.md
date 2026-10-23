# Style

The hand style is the format. No code formatter runs on Python, TypeScript or Bash; linters check rules, the hand writes the shape. A file that does not read like the examples below is not finished.

## Universal

- Zero comments, zero docstrings, zero `noqa`/`eslint-disable`/`shellcheck disable` inline knobs in source. A line that needs a comment gets a better name or a smaller shape. Lint exceptions live in the manifest, per file, with a reason in the commit.
- Very simple unified names: short, lowercase, one word where one word says it (`users`, `greet`, `settle`, `roll`). A name says what, never how. Private members `_name`; a dispatcher helper `_name_`.
- One blank line is the only vertical separator; never two consecutive blank lines. In Python a blank line follows every definition line with a body; in Bash and TypeScript a blank line follows every definition line whose body has more than one statement and precedes the closing of such a body.
- Column law: Python 120, TypeScript 150, Bash as wide as a readable line (shellcheck decides correctness, not width).
- File law: 100–300 lines is the home of a file; above 400 only with a reason the reviewer accepts. A folder of flat files beats a deep tree.
- Aligned groups: consecutive assignments align on `=`, consecutive dict/object entries align their values, consecutive imports group by origin. Alignment is for groups of related lines, never for a single line.
- Imports: third-party and engine first, then the local part, then one combined standard library line at the end (`import asyncio, time`). No wildcard imports, no `import x as y` to dodge a lint.
- Strings: double quotes in Python and TypeScript, single quotes in YAML where quoting is needed. f-strings over concatenation. A long message lives in a variable, not inline in a raise.
- Error handling: no bare `except`, no swallowed exception, no `print` outside command entry points. Failures become the one typed fault of the part with a code and a reason.
- Typing: every public parameter, return and exported contract is annotated; no implicit `Optional`, no `Any` outside an explicit boundary, no non-null assertion in TypeScript.

## Python

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, cast

from engine.error import Code, Fault
from engine.log import log
import asyncio, time

type Loader[T] = Callable[[], Awaitable[T]]

LIMIT = 512

@dataclass(frozen=True, slots=True)
class Hit:

    allowed   : bool
    remaining : int
    reset     : float

class Store(Protocol):

    async def get ( self, key: str ) -> object | None: ...

    async def set ( self, key: str, value: object, ttl: float | None = None ) -> None: ...

class Cache:

    def __init__ ( self, store: Store ) -> None:

        self._store = store
        self._lock  = asyncio.Lock()

    async def remember [T] ( self, key: str, ttl: float, loader: Loader[T] ) -> T:

        found = await self._store.get(key)

        if found is not None: return cast("T", found)

        value = await loader()

        await self._store.set(key, value, ttl)

        log.debug("cache.filled", key=key, ttl=ttl)

        return value

    async def hit ( self, key: str, limit: int, window: float ) -> Hit:

        if limit <= 0: raise Fault(Code.BAD_REQUEST, reason="cache.limit")

        count = await self._store.increment(key, ttl=window)
        left  = await self._store.ttl(key)

        return Hit(allowed=count <= limit, remaining=max(limit - count, 0), reset=time.time() + (left or window))
```

- Definition sites get a space before `(` and inside the parentheses: `def get ( self, key: str ) -> str:`; `class Hit:` has no parentheses when it inherits nothing. Calls, literals and subscripts are tight: `found = store.get(key)`, `items[0]`, `{ "a": 1 }` is written `{"a": 1}` inline and aligned with spaces when multi-line.
- A short branch is a one-liner: `if found is None: return None`. Every `def` and `class` header with a body on its own lines is followed by one blank line, even when the body is a single statement (a law test enforces it); a stub whose body sits on the header line (`def get ( self ) -> int: ...`) stays inline.
- A long signature puts its parameters on 8-space continuation lines and the closing `) -> T:` on its own line.
- Constants are module-level upper case; module-level type aliases use `type X = …`; generics use the 3.12+ syntax.
- A class is the namespace; a package's `__init__.py` does `from .x import X` then aligned lowercase singletons and an explicit `__all__`; constructors do no I/O (I/O happens in the lifespan).
- Dataclasses are `frozen=True, slots=True` (models add `kw_only=True`); protocols describe ports; `StrEnum` for closed vocabularies with behavior on the cases.
- `@asynccontextmanager` functions are typed `AsyncGenerator[T]`; async code uses `TaskGroup`, bounded fan-out, `asyncio.timeout`, explicit cancellation and shutdown; nothing blocks the event loop.
- `if __name__ == "__main__":` is followed by a blank line, then the body.

## TypeScript and TSX

```ts
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { compact } from "engine/base";
import type { Messages } from "engine/translate";
import { securityHeaders } from "./security.ts";

export type Served = { path: string; status: number } | null;
export type Encoding = "br" | "gzip" | null;

const year = "public, max-age=31536000, immutable";
const fresh = "no-cache";

function file ( path: string ): boolean {

    return existsSync(path) && statSync(path).isFile();

}
export function locate ( folder: string, pathname: string ): Served {

    for ( const candidate of candidates(pathname) ) {

        const path = resolve(folder, `.${candidate}`);

        if ( !path.startsWith(folder + sep) ) return null;
        if ( file(path) ) return { path, status: 200 };

    }

    const missing = resolve(folder, "404.html");

    return file(missing) ? { path: missing, status: 404 } : null;

}
export function headersFor ( path: string, status: number, security: Record<string, string> = securityHeaders({}) ): Record<string, string> {

    const html = path.endsWith(".html");
    const cache = html || status !== 200 ? fresh : year;

    return { ...security, "Cache-Control": cache };

}
```

- 4-space indent, double quotes, semicolons, trailing commas on multi-line literals, `.ts`/`.tsx` extensions on relative imports, `import type` for types, `@/…` for the part's own source and `engine/<member>` for the engine (never a relative path into it).
- Function definitions get spaces inside the parentheses (`function f ( a: T ): R {`, `( x ) => x + 1`), conditions get spaces inside (`if ( ok ) {`, `for ( const x of xs ) {`); calls are tight (`f(a, b)`).
- A block of more than one statement opens with a blank line after `{` and closes with a blank line before `}`; a one-statement branch is a one-liner (`if ( !note ) return null;`).
- `const` by default, no `let` where a conditional expression suffices, no `any`, no `!`, no `as` except at validated boundaries (`satisfies` over `as` for literals), no parameter reassignment.
- A component is a function with a typed `Props`; on the web element state travels through `data-*` attributes and one class per element, in React Native through `StyleSheet` objects built from the palette and the spacing, radius and type scales, in elements only; hooks live in `hooks/`; `"use client"` only where a client boundary is required.
- Exported types first, constants next, helpers next, the exported functions last; one default export per element/component/feature entry, named exports elsewhere.

## Bash

- Bash 5+ with four-space indentation. Use lowercase, descriptive function names with hyphen-separated words; put a space before the empty parentheses and opening brace.
- Leave one blank line after a function opens and before it closes. Keep related definitions together and separate logical groups with one blank line; never consecutive empty lines.
- Declare initialized locals first. Preserve valid Bash assignment syntax; align short decision tables only where it improves reading.
- Prefer early guards and compact branches for simple conditions; expand longer conditionals, cases and loops. Use Bash conditional/arithmetic forms and preserve argument vectors with quoted expansions.
- Set strict error, unset-variable and pipeline handling at the entrypoint. Propagate failures explicitly and distinguish deliberate false predicates from command failures.
- No explanatory source comments, purpose/help comments or inline ShellCheck suppressions. Shebangs are executable metadata. Env files alone allow one owner comment above each block; CLI help is structured data.
- Data uses `out` (one literal line per argument); diagnostics use `info succ warn err`, which redact secret values. Predicates are silent. A failure prints one `err` line and returns: `[[ -n "${1:-}" ]] || { err "Value required"; return; }`. No manual status codes outside signal traps.
- `check` enforces the layout, the layer calls (`module/<tool>.sh` calls core and `docker` only, `app/<stack>/` orchestrates), the name prefixes (`<tool>-*`, `<stack>-*`, `config-*`, `bootstrap-*`, `test-*`, `fixture-*`) and every rule of this section on sources and tests.
- Tool metadata, versions, checksums and engineering constants belong to Bash.toml; runtime settings and secrets belong to the one env schema. No Bash formatter; checks enforce the agreed manual style.

```bash
docker-network () {

    local name="${1}" owner="${2}" label=""

    if docker network inspect "${name}" >/dev/null 2>&1; then
        label="$(docker network inspect --format '{{index .Labels "io.infra.owner"}}' "${name}")" || return
        [[ "${label}" == "${owner}" ]] || { err "Network ${name} belongs to ${label:-another owner}"; return; }
        return 0
    fi

    docker network create --label "io.infra.owner=${owner}" "${name}" >/dev/null || { err "Network creation failed: ${name}"; return; }

}
```

## CSS

- `styles/tokens.css` is the only file with raw values; every other stylesheet uses tokens. Tailwind v4 utilities appear only inside `elements/` and `icons/`, built from `std/style` `variants` over the tokens (no arbitrary raw values, no opacity modifiers); states go through `data-*` and `aria-*` variants; no inline styles except custom properties a layout computes (`--cell-size`).
- Light and dark are separate art directions sharing the tokens' names; RTL and LTR, reduced motion and keyboard focus are designed from the start.

## YAML, TOML, JSON, Markdown

- Prettier formats YAML, JSON and Markdown (2-space indent, 120 columns, single quotes in YAML where quoting is needed, prose preserved); taplo formats TOML (4-space indent, 100 columns). These are the only formatters that run; they are run before any check, and their output is accepted as is.
- Workflow and compose YAML: lists in flow style only when they are short (`[main]`, `[web]`), keys in the order they are read, one blank line between top-level keys.
- Markdown starts with the subject, never with a preamble; headers are nouns; tables for parallel facts; code blocks for anything executable.

## What the machine checks and what the hand checks

| Checked by tools                                                                                                                                                                                                                                                                                                                                                                                           | Checked by the hand and the reviewer                                                                                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ruff (every rule), mypy strict, Biome, TypeScript strict, shellcheck, the engine and api law tests (blank lines, comments, import direction, the engine DAG, stdlib above the engine, migrations without SQL, facades), the surface analyzer for web and mobile (layers, imports, styles, 150 columns, 400 lines), the engine/bun runtime-agnostic lint, the infra bootstrap (layout, bundles, ShellCheck) | Spaces in definition parentheses, alignment of groups, one-liners for short branches, naming quality, file size, the shape of a module (types → constants → helpers → public), the thinness of the layers above the engine |
