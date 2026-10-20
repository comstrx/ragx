# Web

One Next.js engine on Bun under `web/`, spec-driven: a TypeScript standard library in `src/lib/std`, a spec DSL in `src/lib/spec`, a rendering tree in `src/app`, and declarative specs under `specs/` (`super` and `admin` panels, `client` site). Gate: `bun run check`, `bun run typecheck`, `bun test`, `bun run build`, `bun run audit` (`bun run gate` chains them).

## Layout and layering

```
web/
├── src/
│   ├── lib/std/        the engine: api array base cache client cookie device error file interact log net parse screen socket spec state storage string style tooling translate validate world
│   ├── lib/providers/  the only other place that imports third parties (device, storage)
│   ├── api/core/       reasons and shared api facts        api/features/<name>.ts   one contract per feature
│   ├── types/          shared types (spec.d.ts, view types shared by hooks and components)
│   ├── lib/spec/       the spec DSL, the validator, routing facts (surface config runtime browser feature routes languages theme)
│   ├── lib/seo/        pure metadata, structured data, robots, sitemap over a Site facts object
│   ├── lib/observe/    observability
│   ├── stores/  hooks/  elements/  icons/  styles/  components/  features/<name>/{index.tsx, components/, hooks/}
│   ├── app/            [locale]/{layout, providers, error, not-found, [[...path]]/{page, screen, blocks, mount, warm, gate, boundary, client-only, missing}}  manifest robots sitemap
│   └── proxy.server.ts the request door of the Next server (dev and standalone), never part of an export
├── specs/<spec>/{config/{index,contents,contracts,features,settings,themes}.ts, schema/{index,<screen>}.ts, brand/{images,fonts,videos,audios,messages}}
├── tools/{core,compile,boot,theme,security,serve,audit}.ts
├── tests/  flat *.test.ts(x)      benches/  flat *.bench.ts
├── messages/  core dictionaries per locale
└── package.json  biome.json  bunfig.toml  tsconfig.json  next.config.ts  postcss.config.mjs
```

Layer order, enforced by the analyzer in `tools/core.ts` (`bun run check`), lowest first:

```
lib/std → lib/providers · api/core · types · specs → api/features → lib/spec → lib/seo → lib/observe → stores
        → hooks · features/*/hooks → elements · icons · styles → components · features/*/components → features → app · proxy.server.ts
```

- A layer imports only lower layers. Only `lib/providers/` and `lib/std/` import third parties; `react`, `next` and `server-only` are foundation.
- **Elements** (`elements/`, flat, one file each) are the only files with HTML and classes. An element imports `icons/`, `lib/std/`, `lib/providers/` and `types/` only, never another element; its props are semantic (`size`, `tone`, `width`, `level`, states) and refuse `className`, `style` and HTML attribute bags (`ComponentProps`, `*Attributes`). It owns its interaction mechanics (focus, keyboard, overflow, dismissal) through `lib/std/interact`, never business or data fetching. Composition happens by slots the caller fills (`Notice` takes its `action`).
- **Icons** (`icons/`) import `lib/std/` and `types/` only.
- **Components** (`components/`, flat, one file each) compose elements, icons and other components (no cycles) and may import exactly one hook, their own `hooks/use-<component>.ts`; no HTML, no classes, no other import. Shared view-model types live in `types/`, so hooks and components never reach upward for them.
- **Features** are `features/<name>/{index.tsx, components/, hooks/}`: the entry imports its own components only and declares `"use client"` or `server-only` as its contract says; feature components build on components, never elements; logic lives in `features/<name>/hooks`. A feature folder needs `api/features/<name>.ts`, and a contract that declares a view needs `features/<name>/index.tsx`.
- **Hooks** rest on `lib/std`: a reusable mechanism sinks into the std, a business decision stays in the hook.
- `@spec/*` virtual modules have one owner each (`lib/spec/config.ts`: `routing settings`; `runtime.ts`: `config schema messages`; `browser.ts`: `browser`; the layout: `theme.css`; `mount.ts`: `mount`; `warm.ts`: `preload`; `blocks.tsx`: `registry`). Specs import the door `@/lib/spec/surface` only, and spec strings avoid branching words because the analyzer scans compiled literals.
- Line law 150 columns over `src tools tests benches specs`; Biome: no `any`, no `!`, no unused, no console, no shadowed globals, `import type`, `useConst`, a11y errors on, files ≤ 400 lines; the formatter is off.

## Feature contracts

`api/features/<name>.ts` is the feature's whole contract, in two separate sections:

```ts
export default contract({
    transport: feature({ cache: 30 }, { read: get("/hello", { name }, greeting) }),
    view: { owner: "client", options: { fallback: "", live: "", saved: "", loading: "", failed: "", offline: "", cached: "" }, ports: { greeting: { kind: "one", fields: ["message"] } } },
});
```

- `transport` is the backend contract (endpoints, inputs, response shapes, permissions); `view` is presentation (owner, literal option defaults, ports, access, signals). Changing how a feature looks never touches its transport, and the reverse.
- `api/features/index.ts` gathers `contracts` and derives `endpoints = transportsOf(contracts)` (the catalogue) and `views = viewsOf(contracts)` (the manifests the tooling validates with `viewFacts`). A transport-only contract (`site: document("content")`) has no feature folder.
- A feature that reads names its `loading failed offline cached` texts (and `empty` when it lists); a query-, signal- or live-bound port needs a client-owned feature, because server pages are static.

## The std library

`lib/std` is the web's core: every protocol, provider and browser/runtime detail lives there; the layers above compose its verbs.

| Member                                                                           | Owns                                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api`                                                                            | the typed client over the api envelope: connections, contracts, execution and encoding options, in-flight read dedupe by url + tenant + auth + language + currency, `browserConfig`, `connectionOrigins`                        |
| `client` `net` `socket`                                                          | fetch, retries, timeouts, content security policy helpers, websocket frames                                                                                                                                                     |
| `cache` `storage` `cookie` `state`                                               | memory and persistent caches, web storage and cookie jars (`jarStore`, `preferenceNames`, `preferenceJar`), zustand-backed stores with whole-document or per-field (`persist.fields`) persistence that writes only what changed |
| `spec`                                                                           | the generic surface compiler (`compileSurface`, `surfaceValidator`, `backendOf`, `transportIssues`, `mergeTheme`) and feature contracts (`contract transportsOf viewsOf`)                                                       |
| `translate`                                                                      | dictionaries and plural rules, and the url contract (`Routing{localized}`, `splitLocale prefixed hrefOf chosenLocale routable routeOf switched`) shared by the proxy and the release server                                     |
| `screen`                                                                         | the runtime (`defineRuntime`, `matchScreen`, `menuOf`, `linkedFeatures`, boundaries) and document verbs (`titleOf titled held isCurrent themeOn separator`)                                                                     |
| `style`                                                                          | `variants(base, axes, defaults)` (memoized per combination, numeric keys allowed) and `classes(...parts)`                                                                                                                       |
| `interact`                                                                       | DOM interaction mechanics for elements: `useOverflow` (edges in both writing directions, stride scrolling), `useDismiss` (outside press, Escape), `rove` (arrow keys, Home, End, wrap, RTL flip)                                |
| `tooling`                                                                        | `createTools` (spec loader over `views`, architecture rules, messages, assets, fonts, icons, build), `deployedContracts`, `measured` and `breaches` (p99 budgets for benches)                                                   |
| `validate` `parse` `string` `array` `base` `error` `log` `file` `device` `world` | zod adapters, parsers, verb sets, the unified error, structured logs, files, device facts, world data (countries, currencies, languages, emojis, icon names)                                                                    |

A missing verb is added to its std member with a test in `tests/<member>.test.ts` and, when hot, a bench in `benches/<member>.bench.ts`; a feature never re-implements a std verb.

## Specs

Each spec is data: `config/` (contents, contracts, features, settings as the delta over the defaults, themes), `schema/` (screens), `brand/` (assets and messages). Under `specs/`, a folder written `(name)` is a transparent group at any depth; the first plain folder is the spec; the identity is the leaf name; `NEXT_PUBLIC_SPEC` takes the identity or the on-disk path.

- `settings.output`: `export` (static files in `.next/out`, served by `tools/serve.ts`) or `standalone` (the Next server, launched by the same `bun run start`).
- `settings.localization` (default `false`): `true` puts every locale in the url (`/en/…`, `/ar/…`, hreflang alternates, `/` sends a visitor to the saved, then the browser's, then the default language with `307` and `Vary: Accept-Language, Cookie`); `false` keeps one url per screen (`/items`), the language is a preference cookie, a locale in the url answers `308` to the bare path, and both the proxy and the release server rewrite to the chosen locale's static page. The validator refuses an indexed spec in several languages without localization.
- `screen.render`: `server` or `client` (default). Indexing is behavior, never a flag: a screen is indexed when it renders on the server, is open and is not `index: false`; a spec is crawlable when it has an indexed screen and `contents.url`.
- **Validator laws** (`tests/specs.test.ts`): an indexed screen needs `contents.url`; `index: true` on a client-rendered or gated screen is refused; robots rules without an indexable screen are refused; `contents.seo.sitemap` is always refused; an export cannot build `:param` paths nor server-render backend reads; a gated screen is always client and never indexed; server-owned features are refused on client screens; a cleartext production url needs `options.insecure: true`; localization as above.
- `deployedContracts`: `SPEC_API_URL` at build time replaces `contracts.urls.production` (and `browser`) and closes the cleartext allowance for an https origin.

## Rendering, routing and the document

- `app/[locale]/layout.tsx` is the root layout (`<html lang dir>` from the locale, `generateStaticParams` over the enabled locales, `dynamicParams = false`, `siteMetadata`, viewport, the boot script) → `[[...path]]/page.tsx` (static: `generateStaticParams`, `generateMetadata`, `notFound()`, JSON-LD + `Screen`; it never reads search params, so every known page prerenders) → `screen.tsx` (shell parts, boundary, suspense, `ClientOnly` for client screens, the gate, and `elements/pending` as the default loader when `screen.loader` is on and no shell loader is placed) → `blocks.tsx`.
- `/` has no page: in dev and standalone `src/proxy.server.ts` routes it (and every other path) with `routeOf`, marking its rewrites with `x-routed` because Next runs the proxy again on the rewritten path; an export ships a compiled `public/index.html` door when localized, and `tools/serve.ts` applies the same `routeOf` to every request (an export served elsewhere without that rewrite only works localized). `next.config.ts` drops `output` in dev and keeps `*.server.ts(x)` out of export builds through `pageExtensions`. Next's prerender cache rewrites `Vary` on pages it serves after a proxy rewrite; `tools/serve.ts` sets it correctly, so an unlocalized standalone site must not be shared-cached by url alone.
- Titles read `action | page | project`: the metadata template is `%s | Name`, and a feature that switches tabs calls `useTitle(page, action)`, which holds the composed title (`held`) against Next's own head updates while mounted.
- Preferences (`language currency theme`) are plain first-party cookies `<spec>.<key>` (`SameSite=Lax`, `Secure` on https, one year), readable by the proxy, the release server and the boot script, written only when changed; local storage keeps caches only, session storage per-tab drafts and the outbox, and tokens never enter web storage. The boot script sets `data-theme` from the cookie before paint.

## Styles

- Tailwind CSS v4 through `@tailwindcss/postcss`; Sass is not used (Tailwind v4 is its own preprocessor and does not support Sass). `styles/globals.css` is the only entry: `@import "tailwindcss" source(none)`, the tokens, `@source "../elements"` and `@source "../icons"` (classes are generated from the markup layers only), and a base layer for focus, selection, scrollbars, view transitions and reduced motion.
- `styles/tokens.css` is the only file with raw values: `@theme { --*: initial; … }` replaces Tailwind's defaults with the product's scales (breakpoints; spacing with `control-*` and `glyph-*` sizes; containers `narrow prose wide`; type; weights; tracking; radius by category `control-*` (inputs and buttons), `panel-*`, `glyph-*` (icon containers and tabs), each `sm md lg xl`; easing; `enter exit reveal spin` animations) and `@theme inline` maps the spec palette (`--body --panel … --info`) to colors plus `hover press active glow` tints, edge colors and the `control panel-* overlay` shadows, whose shades and highlight are redefined for dark: light and dark are separate art directions.
- Element classes may name tokens only: an arbitrary value with a raw literal (`w-[13px]`, `bg-[#f00]`) or an opacity modifier (`bg-primary/40`) is refused by `bun run check`. Variants come from `std/style` `variants`; states use `data-*` and `aria-*` variants.
- Scrollbars are thin and appear only on `html` and on regions marked `data-scroll`; motion follows `--motion-*` tokens that drop to zero under reduced motion; logical properties (`start end ms me ps pe`) keep RTL exact. The icon font already draws direction-aware chevrons in RTL, so glyphs are never flipped by hand.
- Virtualization, when a list needs it, is `virtua` behind `lib/providers/virtual.ts` (`@tanstack/react-virtual` is flagged incompatible with the React Compiler); the viewport sets `height: 100%` inline, so the element sizes its frame, not the list.

## Tooling

- `bun run dev` / `bun run build` compile the spec first (`tools/compile.ts`): `mount.js`, `registry.js`, `preload.js`, `theme.css`, `meta.json` (`output routing reserved language indexed connect secure insecure media security aliases`), `public/_generated/boot.js` and, for a localized export, `public/index.html`.
- `bun run check` = `biome ci .` + `bun tools/core.ts` (architecture, messages, specs, styles and element classes, lines). `bun run typecheck` = compile + `next typegen` + `tsc --noEmit`. `bun test` runs the flat tests. `bun run audit` (after a build) weighs the first load of every locale page with brotli against the budgets in `tools/audit.ts` (export and standalone: html ≤ 4–5 KB, JavaScript ≤ 200 KB, CSS ≤ 12 KB) and checks what crawlers see: `lang`/`dir`, title, `index, follow` or `noindex`, canonical, hreflang for every locale and `x-default`, Open Graph, the Twitter card, the JSON-LD graph, robots and a sitemap with one url per indexed screen and locale. `bun run bench` runs every bench against its p99 budget (`BENCH_SCALE` scales them on a loaded machine).
- `tools/serve.ts` is the release server; the production image bundles it with `bun build --target=bun`.

## Tests and benches

- Flat `tests/*.test.ts(x)` (one per std member plus `architecture`, `specs`, `surface`, `screens`, `seo`, `serve`, `loader`, `elements`, `components`, `style`, `interact`, `audit`, `hygiene`); `bun test` with randomized order. A test compiles a real spec, renders a real element, serves a real folder; an element is tested for every state it renders and its exact classes.
- `benches/*.bench.ts` (mitata) end with `await measured({ name: p99Micros })`; a bench without a budget, a budget without a bench, a thrown bench or a p99 over budget exits 1.

## How to add

- **An element**: `elements/<name>.tsx`, semantic props, `variants` over tokens, `data-*`/`aria-*` states, interaction through `std/interact`, a render test for every state.
- **A component**: one file over elements and components, its logic in `hooks/use-<name>.ts`, shared types in `types/`, a test for each state.
- **A feature**: the contract `api/features/<name>.ts` (`transport` and `view`), registered in `api/features/index.ts`; `features/<name>/index.tsx`, `components/`, `hooks/`; a spec places it with `feature("<name>", …)`.
- **A screen**: `specs/<spec>/schema/<screen>.ts` with `screen({ contents, blocks })`, registered in `schema/index.ts`, messages in the dictionaries; the validator and `tests/specs.test.ts` pin the indexing consequences.
- **A spec**: `specs/<spec>/{config,schema,brand}`, settings as the delta over the defaults (`output`, `localization`, render), contracts naming the api urls, its image built by the infra under `WEB_SPECS`, and `bun run build && bun run audit` green.
- **A std verb**: in its member, exported through the member's index, tested, benched when hot, then consumed.

## UI bar

Every surface is an enterprise product: hierarchy, density, typography, spacing, surfaces, elevation, iconography, motion that explains state, light and dark as separate art directions, LTR and RTL, keyboard and touch, reduced motion. Every important screen handles loading, empty, partial, error, offline, validation failure, permission denial, success, destructive confirmation, long and short content, and missing media. A UI change is rendered, interacted with and inspected at the relevant viewports and themes before it is called done; a defect in a token or primitive is fixed at the token or primitive.
