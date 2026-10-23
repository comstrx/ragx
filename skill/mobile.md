# Mobile

`product/mobile` is one spec-driven Expo and React Native surface engine on Bun over `engine/bun`, the web's twin: the same path, layers, analyzer, spec DSL, feature contracts (`api/core`, `api/features/<name>.ts` word for word), reasons and messages. What differs is the platform only: React Native views instead of the DOM, a router-free navigator instead of Next, Metro and Hermes instead of a Next build. Specs: `admin`, `client`. Gate: `bun run check`, `bun run typecheck`, `bun test`, `bun run export --all`.

## Identity

- The surface for roles that need native reach: push, background audio, voice support and calls, offline queues, secure on-device sessions. Each role is a complete experience from a spec, not a separate app.
- Phone criteria rule: bundle and APK size, start-up time, memory, frame drops, battery; native dependencies stay minimal and each is weighed before it joins. Expo's bundled ranges are the truth (`tests/versions.test.ts`).

## Layout and layers

```
product/mobile/
├── src/
│   ├── lib/providers/  the only third-party imports; `<name>.ts` is the web adapter, `<name>.native.ts` the phone's
│   │                   (device lifecycle random secure storage) + console direction safe-area screens
│   ├── api/core/  api/features/  types/  lib/spec/  lib/observe/  stores/  hooks/  elements/  icons/  styles/  components/  features/<name>/
│   └── render/         app navigator screen page blocks tabs boundary gate (the twin of the web's app/)
├── specs/<spec>/{config,schema,brand}   tools/{core,compile,export,device}.ts   tests/  benches/  flows/  messages/  public/
└── package.json  app.config.ts  metro.config.cjs  babel.config.cjs  index.ts  biome.json  bunfig.toml  tsconfig.json  tsconfig.tools.json
```

```
engine/* → lib/providers · api/core · types · specs → api/features → lib/spec → lib/observe → stores
         → hooks · features/*/hooks → elements · icons · styles → components · features/*/components → features → render
```

- The web's analyzer and Biome wall apply (`a11y security complexity` as errors, 6 parameters, 400 lines, 150 columns, no console outside `lib/providers/console.ts`). `react`, `expo`, `@expo/*` and `engine/*` are foundation; `react-native` is allowed only where markup lives (`elements icons hooks styles`, `lib/providers`); `lib/spec/surface.ts` never reaches it.
- Element, icon, component and feature laws are the web's. Tokens live in `styles/` (`theme palette font`) because React Native has no CSS, so elements and icons read them there and build `StyleSheet` objects from the palette and scales; their props are the web's semantic props, and a heading carries `role="heading"` with `aria-level`.

## Navigation

Router-free: `engine/history` is the brain (`stores/navigation.ts`), `react-native-screens` renders the stack (`render/navigator.tsx`, `elements/screens.tsx`), `hooks/use-router.ts` is the features' door; tabs stay laid out off screen (`elements/panes.tsx`); the React Compiler is on. No expo-router, reanimated, gesture-handler, svg or expo-image.

## Specs

The web's DSL validated by the mobile compiler (`tests/compiler.test.ts`): every feature is client-owned; a tab screen has no path parameters and a gated screen names its redirect; reserved paths (`/_*`, `/+*`, `/(…`, `/api`) are refused; there is no SEO, delivery or session cookie, so SEO fields are refused. `settings.app` names the app (`slug`, `scheme`); `screen.scroll: false` lets a feature own a virtualized list; `EXPO_PUBLIC_SPEC` picks the spec and the identity reaches the app through `Constants.expoConfig.extra.spec`.

## Build

- `app.config.ts` reads the compiled `meta.json` (name, slug, scheme, icon, fonts, the cleartext allowance) and refuses to run before `bun tools/compile.ts <mode>`; `"type": "module"`, so Babel and Metro configs are `.cjs`; two tsconfigs (app with React Native types, tools with Bun's).
- Session in expo-secure-store, caches in async-storage, no expo-sqlite. `tools/export.ts` exports Hermes bytecode per spec (`--all` for every spec); `tools/device.ts` drives a connected phone for flows and start-up numbers (local only).

## Metro laws

- One copy of every host package: an engine import of `react react-native expo …` resolves from the surface, and an undeclared host package fails the bundle; Metro watches the engine's real path through the link.
- No tree shaking: zod's locale and JSON-schema modules resolve to empty; a module importing a generated registry (`@spec/emoji`, `@spec/flags`) stays its own module imported only by its consumers, checked by comparing exported bytecode size and asset count per spec.

## Tests and benches

- `tests/native.ts` (bunfig preload) gives `bun test` Metro's view of the app: `react-native` is served by react-native-web (Expo's own web target), `@spec/*` by the compiled spec, the engine's React by the surface's single copy, asset requires by their paths, and `expo-constants` by the compiled spec identity (the one native module the render chain reads).
- `tests/elements.test.tsx` and `tests/components.test.tsx` render the real elements and components through the real store and palette and assert exact states (heading levels, note tones, alert and action, grid and widths, loader color); `compiler.test.ts` pins the spec laws; `versions.test.ts` the Expo ranges. The engine's members are tested in `engine/bun`.
- `benches/compile.bench.ts` holds p99 budgets for compiling and composing every spec.

## How to add

- **An element, component, feature, screen**: as the web (`web.md`), with React Native markup in the element and a render test per state; the feature's contract file is the web's.
- **A native capability**: a port in the engine member when generic, the `.native.ts` adapter in `lib/providers`, permissions in `app.config.ts`; never a native call in a hook or feature.
- **A spec**: `specs/<spec>/` with `settings.app`, an icon in `brand/images`, its messages, and `export --all` green.

## Traps

- React Native swaps left and right for absolute positions in RTL; `I18nManager.forceRTL` applies from the next launch; a horizontal `ScrollView` in a flex column needs `flexGrow: 0`.
- A text node directly inside a `View` is an error; wrap it in `Text`.
- An Android release build needs `NODE_ENV=production` (expo-constants reads the development cache otherwise); never compile a spec while Gradle bundles; `enableViewCulling` and `enableViewRecycling` crash on React Native 0.86.
