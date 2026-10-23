# Bun engine

`engine/bun` is the TypeScript engine every surface stands on: one package, `engine`, whose members live under `packages/<member>/src/` and are exported one subpath each (`engine/api`, `engine/spec`, `engine/translate` …). It is generic and product-free, shared word for word by `product/web` and `product/mobile`, and an independent workspace with its own manifest, lockfile, tests, benches and gate. Gate: `bun install --frozen-lockfile && bun link`, `bun run check` (tsc + the 150-column law), `bun run lint`, `bun test`, `bun audit` (`bun run gate` chains them).

## Identity

- One coherent TypeScript developer experience, not a pile of libraries: one naming, one failure model, typed contracts, focused public interfaces. Every member justifies itself by reuse or an independent responsibility.
- Product-free: "would this survive deleting every current feature?" No backend shapes, endpoint paths, resource names, business rules, brand values or product names live here, not in `packages/` and not in `tests/` (synthetic fixtures only). The engine gives shapes and `define*` helpers; values (palettes, scales, defaults of a product) live in the surfaces.
- Shared where it matters, specialized where platforms differ: logic, contracts and tokens are unified; DOM components and native views are never forced into one. What differs between web and mobile sits behind an adapter or in a platform member, and each surface keeps its framework's own semantics (Next and the DOM in `product/web`, Expo and React Native in `product/mobile`).

## Layout

```
engine/bun/
├── packages/<member>/src/   index.ts (the member's public surface) + flat files; world also carries data/ and asset/
├── tests/                   flat <member>.test.ts files + members.test.ts (the member laws) + lines.test.ts
├── benches/                 flat <member>.bench.ts files, each ending in measured({ name: p99Micros })
├── tools/lines.ts           the 150-column law over packages, tests, benches, tools
├── node_modules/            the only one: every dependency of every member, isolated linker, exact pins, 3-day release age
├── .bun/                    the link registry the surfaces resolve `link:engine` through
└── package.json  bun.lock  bunfig.toml  biome.json  tsconfig.json
```

A member is a folder, not a package: it has no manifest and never a `node_modules` of its own.

## Facade and link

- `package.json` is the one package `engine` (no workspaces); `exports` maps `./<member>` → `./packages/<member>/src/index.ts` and nothing else. Every import, inside the engine and in the surfaces, is `engine/<member>`; a relative import never crosses into another member, and a member's index exports only what something outside it uses.
- Every external dependency sits at the root once: `zod zustand lucide-static subset-font mitata`, React as a peer. A surface never re-declares them.
- The surfaces depend with `"engine": "link:engine"`, and every bunfig shares one global directory (`engine/bun/.bun`; the surfaces point at `../../engine/bun/.bun`): `bun install && bun link` in `engine/bun` registers it, then each surface installs. Next compiles it through `transpilePackages: ["engine"]` and traces from the common root of the surface and the engine; Metro watches the engine's real path and resolves host packages (React, React Native, Expo) from the surface, so one copy of each ships.
- The day the engine leaves for its own repository, the surfaces swap `link:engine` for a release reference and nothing else changes.

## Members

| Member                                                                           | Owns                                                                                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api`                                                                            | the typed client over the api envelope: connections, contracts, execution and encoding options, in-flight read dedupe by url + tenant + auth + language + currency, `browserConfig`, `connectionOrigins`                                                                         |
| `client` `net` `socket`                                                          | fetch, retries, timeouts, content security policy helpers, websocket frames                                                                                                                                                                                                      |
| `cache` `storage` `cookie` `state`                                               | memory and persistent caches, web storage and cookie jars (`jarStore`, `preferenceNames`, `preferenceJar`), zustand-backed stores with whole-document or per-field (`persist.fields`) persistence that writes only what changed                                                  |
| `spec`                                                                           | the generic surface compiler (`compileSurface`, `surfaceValidator`, `backendOf`, `transportIssues`, `mergeTheme`) and feature contracts (`contract transportsOf viewsOf`)                                                                                                        |
| `translate`                                                                      | dictionaries and plural rules, and the url contract (`Routing{localized}`, `splitLocale prefixed hrefOf chosenLocale routable routeOf switched`) shared by the proxy and the release server                                                                                      |
| `screen`                                                                         | the runtime (`defineRuntime`, `matchScreen`, `menuOf`, `linkedFeatures`, boundaries) and document verbs over structural targets (`titleOf titled isCurrent themeOn separator`)                                                                                                   |
| `style`                                                                          | `variants(base, axes, defaults)` (memoized per combination, numeric keys allowed) and `classes(...parts)`                                                                                                                                                                        |
| `interact`                                                                       | the DOM member: interaction mechanics for web elements, `useOverflow` (edges in both writing directions, stride scrolling), `useDismiss` (outside press, Escape), `rove` (arrow keys, Home, End, wrap, RTL flip), and `held` (a title kept against the framework's head updates) |
| `history`                                                                        | the router-free navigator's brain for surfaces without a url router: `createHistory`, `parseHref`, `formatHref`                                                                                                                                                                  |
| `tooling`                                                                        | build time only: `createTools` (spec loader over `views`, the surface analyzer, messages, assets, fonts, icons, build), `deployedContracts`, `lineIssues` (the column law), `measured` and `breaches` (p99 budgets for benches)                                                  |
| `validate` `parse` `string` `array` `base` `error` `log` `file` `device` `world` | zod adapters, parsers, verb sets, the unified error, structured logs, files, device facts, world data (countries, currencies, languages, emojis, icon names)                                                                                                                     |

Members reach each other in one direction; `tests/members.test.ts` refuses a cycle, an unknown member, a cross-member relative import or an export that is not one member's index:

```
array base history style       → nothing        error  → base            cache   → base           storage → error
string → array                  parse → base error                         validate → base error    log     → error
file   → error parse            device → error file                        net      → base error parse
translate → base error parse    world → base string                        state    → base storage   socket  → base error log
cookie → base storage translate validate                                   api      → array base cache error file net parse validate
spec   → api array base net parse string translate validate               screen   → array parse spec translate
interact → screen               tooling → array base spec translate validate world
client → api array base cache device error file screen spec state storage translate validate
```

## Laws

- **Runtime law** (Biome): a member runs on the browser, Bun, Node and Hermes alike; `Bun`, `process`, `Buffer`, `require`, `node:*` and `bun:*` are refused in `packages/` except `tooling`, which runs at build time only. DOM-only mechanics live in `interact`, the one member a native surface never imports; socket and body types are structural.
- **Render law**: no hook reads a browser global at render (a render-time `window.location` breaks server rendering); `tests/client.test.ts` proves it with `renderToString`. Hooks are `use<Name>`; a store binding exposes `useSelect`, never a plain `use` (the React Compiler reads `x.use()` as React's `use()`).
- **Credential law**: a spec never holds a credential-shaped value; real values live in the surfaces' ignored env files and reach a build through the environment.
- **Security**: a queued write lives in the outbox of its owner (`<identity>.outbox.user:<id>` or `.guest`) and is never replayed under another user; the compiler refuses a cleartext production address unless `options.insecure: true`; `forwardedFor` trusts exactly the configured number of proxy hops.
- **States law**: a client feature with a read port names its `loading failed offline cached` texts (a list also `empty`); the compiler fills omitted ones from the surface's `state.*` messages and refuses an explicitly empty one.
- **Lint wall** (Biome): recommended plus correctness, style, suspicious, a11y and security as errors; no `any`, no `!`, no unused, no console, `import type`, `useConst`, at most 6 parameters, at most 400 lines per file; the formatter is off. The column law (150) runs in `bun run check`.

## Tests and benches

- Flat `tests/<member>.test.ts` files, `bun test` in random order; a test drives the real member (a real compiled spec, a real store, a real socket frame) and its failure path. `contract.fixture.test.ts` freezes the wire contract in `tests/fixtures.json`; `perf.test.ts` holds median budgets; `architecture.test.ts` and `tooling.test.ts` pin the surface analyzer and the build tools over synthetic surfaces.
- `benches/<member>.bench.ts` (mitata) end with `await measured({ name: p99Micros })`; a bench without a budget, a budget without a bench, a thrown bench or a p99 over budget exits 1; `BENCH_SCALE` widens budgets on a busy machine.

## How to add

- **A verb**: in its member, exported through the member's index, tested in `tests/<member>.test.ts`, benched when hot, then consumed by the surfaces in one line. A surface never re-implements a verb the engine owns.
- **A member**: `packages/<name>/src/index.ts`, one `./<name>` export in `package.json`, a test file, a place in the DAG above; the member law test refuses anything less.
- **A platform difference**: a port in the member and an adapter per runtime (a web adapter beside it, a native one in the surface's `lib/providers`), never a runtime check inside shared logic.

## Traps

- Write combining marks in regexes as `\uXXXX`; a pasted literal once stripped every Arabic letter.
- Biome's import ordering sorts `engine/*` with the third parties; its safe fix is the only machine edit allowed on TypeScript.
