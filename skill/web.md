# Web

`product/web` is one spec-driven Next.js surface engine on Bun over `engine/bun`. It builds any number of products from `specs/` alone: client-only exported panels (`super`, `admin`) and a server-rendered, indexable site (`client`). Its layers, specs and feature contracts are shared word for word with `product/mobile`. Gate: `bun run check`, `bun run typecheck`, `bun test`, `bun run deliver --all` (`bun run gate` chains them).

## The path

`elements/` + `icons/` → `components/` → `features/<name>/` → `api/features/<name>.ts`, rendered from `specs/<spec>/schema`.

- **Elements** are the only files with HTML, Tailwind classes and tokens. One job each, opinionated in design, adapted only through semantic props (`sm md lg xl full auto disabled hoverable soundable`, `tone width level` and states); `className`, `style` and HTML attribute bags are refused. An element imports `icons/ styles/ engine/* lib/providers/ types/` only, never another element; it owns its focus, keyboard, overflow and dismissal through `engine/interact`; composition happens through slots.
- **Icons** import `styles/ engine/* types/` only. **Components** compose elements, icons and components (no cycle) and import exactly one hook, `hooks/use-<component>.ts`; no HTML, no classes (needing them means an element is not trained enough); 5–200 lines is their natural size.
- **Features** are `features/<name>/{index.tsx, components/, hooks/}`: a thin entry over its own components, feature components built on components, never elements; the business decision lives in the feature's hooks. Components feed features, so a feature never builds a complex piece from scratch.
- **The engine boundary** is responsibility: a reusable mechanism sinks into `engine/bun`; a business decision stays in a hook or feature. Every unit justifies itself by reuse or an independent responsibility; file counts and fashionable libraries are never goals, and the purity of elements and components decides the surface's quality.

## Layout and layers

```
product/web/
├── src/
│   ├── lib/providers/  the only third-party imports (device, storage)
│   ├── api/core/       reasons and shared api facts        api/features/<name>.ts  one contract per feature
│   ├── types/  lib/spec/ (the DSL, validator, routing facts)  lib/seo/  lib/observe/
│   ├── stores/  hooks/  elements/  icons/  styles/  components/  features/<name>/
│   ├── app/            [locale]/{layout, providers, error, not-found, [[...path]]/{page, screen, blocks, mount, warm, gate, boundary, client-only, missing}}
│   └── proxy.server.ts the request door in dev and standalone, never in an export
├── specs/<spec>/{config/{index,contents,contracts,features,settings,themes}.ts, schema/{index,<screen>}.ts, brand/{images,fonts,videos,audios,messages}}
├── tools/{core,compile,deliver,boot,theme,security,serve,audit}.ts
├── tests/  benches/  messages/  public/
└── package.json  biome.json  bunfig.toml  tsconfig.json  next.config.ts  postcss.config.mjs
```

```
engine/* → lib/providers · api/core · types · specs → api/features → lib/spec → lib/seo → lib/observe → stores
         → hooks · features/*/hooks → elements · icons · styles → components · features/*/components → features → app · proxy.server.ts
```

The analyzer (`tools/core.ts`, `bun run check`) enforces the order, the import rules above, `@spec/*` owners (`lib/spec/config.ts` routing and settings, `runtime.ts` config/schema/messages, `browser.ts`, the layout's theme, `mount.ts`, `warm.ts`, `blocks.tsx` registry), specs importing only `@/lib/spec/surface`, a 150-column law and the class law; Biome refuses `any`, `!`, unused code, console, files over 400 lines; the formatter is off.

## Feature contracts

```ts
export default contract({
    transport: feature({ cache: 30 }, { read: get("/hello", { name }, greeting) }),
    view: { owner: "client", options: { fallback: "", live: "", saved: "", loading: "", failed: "", offline: "", cached: "" }, ports: { greeting: { kind: "one", fields: ["message"] } } },
});
```

- `transport` is the backend contract (endpoints, inputs, shapes, permissions); `view` is presentation (owner, literal option defaults, ports, access, signals). A look never touches a transport, and the reverse.
- `api/features/index.ts` gathers `contracts` into `endpoints = transportsOf(...)` and `views = viewsOf(...)`; a transport-only contract (`site: document("content")`) has no folder. A reading feature names its `loading failed offline cached` texts (and `empty` for lists); query-, signal- or live-bound ports need a client-owned feature.

## Specs

- A spec is data: `config/` (contents, contracts, features, settings as a delta over defaults, themes), `schema/` (screens), `brand/` (assets, messages). `(name)` folders are transparent groups at any depth; the first plain folder is the spec; `NEXT_PUBLIC_SPEC` takes the identity or the path. The vocabulary stays small, consistent and composable and refuses invalid combinations at compile time; a new difference is not automatically a new option; custom endpoints in a spec only in the darkest case.
- `settings.output`: `export` (static `.next/out`, served by `tools/serve.ts`) or `standalone` (the Next server through the same `bun run start`). `settings.localization`: `true` puts the locale in every url with hreflang and a `307` from `/` by saved, browser, default language (`Vary: Accept-Language, Cookie`); `false` keeps one url per screen with the language as a cookie and a `308` from a locale url.
- Indexing is behavior, never a flag: a screen is indexed when it renders on the server, is open and not `index: false`; a spec is crawlable with an indexed screen and `contents.url`. Panels export client-rendered with noindex, disallow-all robots and an empty sitemap without saying so.
- **Validator laws** (`tests/specs.test.ts`): an indexed screen needs `contents.url`; `index: true` on a client or gated screen, robots rules without an indexable screen and `contents.seo.sitemap` are refused; an export cannot build `:param` paths or server-render backend reads; a gated screen is client and never indexed; server-owned features are refused on client screens; a cleartext production url needs `options.insecure: true`; an indexed multi-language spec needs localization.
- `SPEC_API_URL` at build time replaces the production contract url and closes the cleartext allowance for https.

## Rendering

- `app/[locale]/layout.tsx` (`<html lang dir>`, static params per locale, metadata, viewport, the boot script) → `[[...path]]/page.tsx` (static params, metadata, `notFound()`, JSON-LD; never reads search params, so every page prerenders) → `screen.tsx` (shell, boundary, suspense, `ClientOnly`, the gate, the default loader) → `blocks.tsx`.
- `/` has no page: `proxy.server.ts` routes it with `routeOf` (rewrites marked `x-routed`); a localized export ships a compiled `public/index.html`; `tools/serve.ts` applies the same `routeOf` and sets `Vary` correctly.
- Titles read `action | page | project`; `useTitle(page, action)` holds the composed title against Next's head updates (`engine/interact` `held`).
- Preferences (`language currency theme`) are first-party cookies `<spec>.<key>` (`SameSite=Lax`, `Secure` on https, one year), written only when changed; local storage keeps caches, session storage per-tab drafts and the outbox; tokens never enter web storage. The boot script sets `data-theme` before paint.

## Styles and design

- Tailwind v4 through PostCSS (no Sass). `styles/globals.css` imports Tailwind with sources limited to `elements` and `icons`; `styles/tokens.css` is the only file with raw values: product scales (breakpoints, spacing with `control-*`/`glyph-*`, containers, type, radius by category `control-* panel-* glyph-*` each `sm md lg xl`, easing, animations) and the spec palette with `hover press active glow` tints and shadows, redefined for dark: light and dark are separate art directions.
- Element classes name tokens only: raw arbitrary values and opacity modifiers are refused; variants come from `engine/style`; states use `data-*`/`aria-*`. Scrollbars are thin, unified and only on large regions (`html`, sidebars, chat, big panels marked `data-scroll`); motion follows tokens that drop to zero under reduced motion; logical properties keep RTL exact; the icon font flips chevrons itself.
- Radius, shadow, hover, press and focus are unified per category, never per element. Enterprise identity, never the usual AI look; motion explains enter, exit, transitions, popups, sidebars, press and drag. Brand icons are original 3D cartoon art from the brand primary with an orangered/orange/red break for error, empty, celebration, offer, coupon and award states; font icons serve controls. Dropdowns animate; sidebars are vertical tabs with soft hover and an active state just above it; horizontal tabs show scroll buttons only on overflow. A large list, when one arrives, renders with `virtua` behind `lib/providers/virtual.ts`.

## Tooling

- `tools/compile.ts` compiles the spec before dev, build and typecheck (`mount.js registry.js preload.js theme.css meta.json`, `public/_generated/boot.js`, the localized `index.html`). `bun run typecheck` = compile + `next typegen` + `tsc`.
- `bun run deliver [--all]` compiles, builds and audits the selected spec or every installed one; `tools/audit.ts` weighs the first load of every locale page with brotli (html ≤ 4–5 KB, js ≤ 200 KB, css ≤ 12 KB) and checks what crawlers see (`lang dir`, title, robots meta, canonical, hreflang with `x-default`, Open Graph, Twitter, JSON-LD, robots.txt, sitemap).
- `tools/serve.ts` is the release server: export files with immutable hashed assets, or the standalone server it finds under `.next/out/standalone/` (Next traces from the common root of the surface and the engine, so the server sits under `product/web/` there).

## Tests and benches

- Flat `tests/*.test.ts(x)` for what the surface owns (`specs seo serve elements components style talk theme audit`): a test compiles a real spec, renders a real element in every state with its exact classes, serves a real folder. The engine's members are tested in `engine/bun`.
- `benches/*.bench.ts` end with `measured({ name: p99Micros })` and fail on a blown budget, never loosened to pass (`BENCH_SCALE` on a shared machine).
- Tests and benches are chosen for coverage, not count: tens of meaningful tests, a bench per hot path. Dependencies are the newest stable that Bun's `minimumReleaseAge` admits, each chosen for measured value.

## How to add

- **An element**: semantic props, `variants` over tokens, `data-*`/`aria-*` states, interaction through `engine/interact`, a render test per state.
- **A component**: one file over elements and components, its logic in `hooks/use-<name>.ts`, a test per state.
- **A feature**: `api/features/<name>.ts` registered in the index, `features/<name>/{index.tsx, components/, hooks/}`, placed by a spec with `feature("<name>", …)`; the same contract file serves the mobile.
- **A screen / a spec**: `schema/<screen>.ts` with `screen({ contents, blocks })` and its messages; a spec under `specs/<spec>/` with its settings delta, contracts and brand, built by the infra under `WEB_SPECS`, green under `deliver`.
- **An engine verb**: in `engine/bun`, then one line here.

## UI bar

Every surface is an enterprise product: hierarchy, density, typography, spacing, elevation, motion that explains state, separate light and dark art directions, LTR and RTL, keyboard and touch, reduced motion; every important screen handles loading, empty, partial, error, offline, validation, permission, success, destructive confirmation, long and short content, missing media. A UI change is rendered and interacted with at the relevant viewports, themes and directions (Playwright) before it is done.

## Traps

- Export forbids rewrites, redirects, headers, proxy and cookies (even in `next dev`); `pageExtensions` keeps `*.server.ts(x)` out of exports.
- Next re-runs the proxy on its own rewrite and its prerender cache overwrites `Vary`; Next rewrites `<title>` after effects.
- virtua sizes the frame, not the list; `@tanstack/react-virtual` conflicts with the React Compiler.
- Spec strings avoid the analyzer's branching words (`for`, `if`, `=>`).
