# Web

One Next.js engine on Bun under `web/`, spec-driven: a TypeScript standard library in `src/lib/std`, a spec DSL in `src/lib/spec`, a rendering tree in `src/app`, and declarative specs under `specs/` (`super` and `admin` panels, `client` site). Gate: `bun run check`, `bun run typecheck`, `bun test`, `bun run build` (`bun run gate` chains them).

## Layout and layering

```
web/
├── src/
│   ├── lib/std/      the engine: api array base cache client cookie device error file log net parse screen socket spec state storage string tooling translate validate world
│   ├── lib/providers/  the only other place that imports third parties
│   ├── api/core/     reasons and shared api facts        api/features/   feature endpoints (the catalogue)
│   ├── types/        shared types
│   ├── lib/spec/     the spec DSL and the validator (surface, config, runtime, browser, feature)
│   ├── lib/seo/      pure metadata, structured data, robots, sitemap over a Site facts object
│   ├── lib/observe/  observability
│   ├── stores/       zustand stores          hooks/   shared hooks
│   ├── elements/     the only files with HTML: document shell block heading button notice jsonld
│   ├── icons/ styles/  tokens.css (raw values) globals.css elements.css (tokens only)
│   ├── components/   one file each, composed of elements
│   ├── features/<name>/{feature.ts, index.tsx, components/, hooks/}
│   └── app/(root), app/(web)/[locale]/{layout.tsx, [[...path]]/{page.tsx, screen.tsx, blocks.tsx, mount.ts, warm.ts}}
├── specs/<spec>/{config/{index,contents,contracts,features,settings,themes}.ts, schema/{index,<screen>}.ts, brand/{images,fonts,videos,audios,messages}}
├── tools/{core,compile,theme,security,serve}.ts
├── tests/  flat *.test.ts(x)      benches/  flat *.bench.ts
├── messages/  core dictionaries per locale
└── package.json  biome.json  bunfig.toml  tsconfig.json  next.config.ts
```

Layer order, enforced by the analyzer in `tools/core.ts` (`bun run check`), lowest first:

```
lib/std → lib/providers · api/core · types · specs → api/features → lib/spec → lib/seo → lib/observe → stores
        → hooks · features/*/hooks → elements · icons · styles → components · features/*/components → features → app
```

- A layer imports only lower layers. Only `lib/providers/` and `lib/std/` import third parties; `react`, `next` and `server-only` are foundation and allowed everywhere they belong.
- HTML lives only in `elements/`; a component is one file over elements; a feature is `features/<name>/{feature.ts, index.tsx, components/, hooks/}`; `@spec/*` virtual modules have one owner each (`lib/spec/config.ts` owns `routing settings build`; `runtime.ts` owns `config schema messages`; `browser.ts` owns `browser`; the layout owns `theme.css`; `mount.ts` owns `mount`; `warm.ts` owns `preload`; `blocks.tsx` owns `registry`).
- Specs import the door as `@/lib/spec/surface`; relative reach into `src/` is refused. Spec strings avoid branching words (`for`, `if`, `=>`) because the analyzer scans compiled literals.
- Styles law: `styles/tokens.css` is the only file with raw values; `globals.css` and `elements.css` use tokens only; one class per element; states through `data-*`; no Tailwind, no inline styles.
- Line law 150 columns over `src tools tests benches specs`; Biome: no `any`, no `!`, no unused, no console, `import type`, `useConst`, a11y errors on, files ≤ 400 lines; the formatter is off (the hand style formats).

## The std library

`lib/std` is the web's core: every protocol, provider and browser/runtime detail lives there, the layers above compose its verbs.

| Member                                                                                                | Owns                                                                                                                                                                                                             |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `api`                                                                                                 | the typed client over the api envelope: connections, contracts, execution and encoding options, in-flight read dedupe by url + tenant + auth + language + currency, `browserConfig`, `connectionOrigins`         |
| `client` `net` `socket`                                                                               | fetch, retries, timeouts, content security policy helpers, websocket frames                                                                                                                                      |
| `cache` `storage` `cookie` `state`                                                                    | memory and persistent caches, browser storage adapters, zustand-backed state                                                                                                                                     |
| `spec`                                                                                                | the generic surface compiler: `compileSurface`, `surfaceValidator`, `backendOf`, `transportIssues` (cleartext production urls need `options.insecure`), `mergeTheme`, settings resources                         |
| `tooling`                                                                                             | `createTools` (the spec loader, architecture rules, messages, assets, feature facts, fonts, icons, build), `deployedContracts` (the `SPEC_API_URL` override)                                                     |
| `translate` `validate` `parse` `string` `array` `base` `error` `log` `file` `device` `screen` `world` | i18n dictionaries and plural rules, zod adapters, parsers, verb sets, the unified error, structured logs, files, device facts, screen helpers, world data (countries, currencies, languages, emojis, icon names) |

A missing verb is added to its std member with a test in `tests/<member>.test.ts` and, when hot, a bench in `benches/<member>.bench.ts`; a feature never re-implements a std verb.

## Specs

Each spec is data: `config/` (contents, contracts, features, settings as the delta over the defaults, themes), `schema/` (screens), `brand/` (assets and messages). Under `specs/`, a folder written `(name)` is a transparent group at any depth; the first plain folder is the spec; the identity is the leaf name; `NEXT_PUBLIC_SPEC` takes the identity or the on-disk path; an identity shared by two groups is an error; the first installed spec by identity is the default.

```ts
export default {
    output: "standalone",
    mediaOrigins: ["https://media.example.com"],
    screen: { render: "server", nav: false, sidebar: false },
} satisfies SiteConfig["settings"];

export default screen({
    contents: { name: "home", path: "/", title: t("hello.title"), description: t("hello.description"), icon: "house", kind: "page", priority: 1, frequency: "weekly" },
    blocks: [
        block({ width: "narrow", height: "screen", padding: 6, align: "center" }, [
            feature("hello", { heading: true, options: { fallback: t("hello.fallback") }, ports: { greeting: read("hello.read") } }),
        ]),
    ],
});
```

- `settings.output`: `export` (static files in `.next/out`, served by `tools/serve.ts`: CSP, brotli/gzip, weak ETags) or `standalone` (`next build` server, launched by the same `bun run start`, which stages `public/` and `.next/out/static` beside `server.js` once and spawns `node`). `distDir` is always `.next/out`.
- `screen.render`: `server` or `client` (default). A client screen renders inside `ClientOnly` after hydration; a server screen renders on the server; server-owned features (`owner: "server"`) read through the server client; client-owned features mount through `next/dynamic`.
- **Indexing is behavior, never a flag.** A screen is indexed when it renders on the server, is open (`access: any`) and is not `index: false`; a spec is crawlable when it has at least one indexed screen and `contents.url`. Crawlable: per-screen metadata, canonical, hreflang for every enabled locale, Open Graph, Twitter card, `robots.txt`, `sitemap.xml` (indexed screens × locales), JSON-LD graph. Not crawlable: `noindex, nofollow`, `Disallow: /`, an empty sitemap. Both emit `manifest.webmanifest` and theme-color viewport.
- **Validator laws** (compile time, `tests/specs.test.ts`): an indexed screen needs `contents.url`; `index: true` on a client-rendered or gated screen is refused; robots rules without an indexable screen are refused; `contents.seo.sitemap` is always refused (it derives from screens); an export cannot build `:param` paths nor server-render backend reads; a gated screen is always client and never indexed; server-owned features are refused on client screens; a cleartext production url needs `options.insecure: true`.
- `deployedContracts`: at build time `SPEC_API_URL` replaces `contracts.urls.production` (and `browser` when named) and sets `insecure=false` for an https origin; the spec keeps its lab values when the variable is absent. The infra builds every web image with it.

## Rendering tree

`app/(web)/[locale]/layout.tsx` (static locale params, `metadata = siteMetadata()`, viewport, boot script) → `[[...path]]/page.tsx` (server: `generateStaticParams`, `generateMetadata`, `notFound()`, JSON-LD + `Screen`) → `screen.tsx` (shell parts, boundary, suspense, `ClientOnly` for client screens, the gate) → `blocks.tsx` (server features from `@spec/registry` or `Mount` for client features). `/` is a client redirect in export and a server 307 by `Accept-Language` in standalone. No middleware (unsupported in export); every locale lives under its prefix. Standalone production gets the same security headers and CSP as the export server through `next.config.ts` from the compiled `meta.security`.

## Tooling

- `bun run dev` / `bun run build` compile the spec first (`tools/compile.ts`): `mount.js`, `registry.js`, `preload.js`, `theme.css`, `build.json`, `meta.json` (`output indexed connect secure insecure media security aliases`), the boot script and the brand assets.
- `bun run check` = `biome ci .` + `bun tools/core.ts` (architecture, messages, specs, styles, lines). `bun run typecheck` = compile + `next typegen` + `tsc --noEmit`. `bun test` runs the flat tests. `bun run bench` loops the benches.
- `tools/serve.ts` is the release server; the production image bundles it with `bun build --target=bun` to one file so the runtime ships only `.next/out`, `public`, `tools/serve.js` and the compiled `meta.json`, runs read-only as uid 1000 with `/tmp` and the standalone cache on tmpfs.

## Tests and benches

- Flat `tests/*.test.ts(x)` (one per std member plus `specs`, `surface`, `screens`, `seo`, `serve`, `loader`, `elements`, `components`, `hygiene`); `bun test` with randomized order. A test compiles a real spec, renders a real element, serves a real folder; fixtures live beside the tests. A component is tested for every state it renders.
- `benches/*.bench.ts` (mitata) cover the std hot paths (api client, cache, parse, validate, translate, spec compile); a bench fails on a regression beyond its budget; first-load JavaScript of the exports is measured and recorded in `README.md`.

## How to add

- **An element**: `elements/<name>.tsx`, one class, `data-*` states, tokens only, a render test in `tests/elements.test.tsx` covering every state.
- **A component**: one file over elements, no HTML, a test for each state.
- **A feature**: `features/<name>/feature.ts` (owner, options, ports), `index.tsx`, components and hooks inside it; the endpoint in `api/features`; a spec places it with `feature("<name>", …)`; tests for the manifest, the ports and the rendered states.
- **A screen**: `specs/<spec>/schema/<screen>.ts` with `screen({ contents, blocks })`, registered in `schema/index.ts`, messages in `brand/messages`; the validator and `tests/specs.test.ts` pin the indexing consequences.
- **A spec**: `specs/<spec>/{config,schema,brand}`, settings as the delta over the defaults, its contracts naming the api urls (lab values; production is injected by `SPEC_API_URL`), its image built by the infra under `WEB_SPECS`.
- **A std verb**: in its member, exported through the member's index, tested, benched when hot, then consumed; never a local helper in a feature.

## UI bar

Every surface is an enterprise product: hierarchy, density, typography, spacing, surfaces, elevation, iconography, motion that explains state, light and dark as separate art directions, LTR and RTL, keyboard and touch, reduced motion. Every important screen handles loading, empty, partial, error, offline, validation failure, permission denial, success, destructive confirmation, long and short content, and missing media. A UI change is rendered, interacted with and inspected at the relevant viewports and themes before it is called done; a defect in a token or primitive is fixed at the token or primitive.
