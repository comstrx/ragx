import { resolve } from "node:path";
import { catalogueFacts } from "engine/spec";
import { createTools, type Loaded, lineIssues, report, task } from "engine/tooling";
import { reasons } from "../src/api/core/index.ts";
import { endpoints, views } from "../src/api/features/index.ts";
import { type Locale, supportedLocales } from "../src/lib/spec/languages.ts";
import { type Compiled, validateSpec } from "../src/lib/spec/surface.ts";

export type Spec = Loaded<Compiled, Locale>;

const columns = 150;
const sources = ["src", "tools", "tests", "benches", "specs"];

export const tools = createTools<Compiled, Locale>({
    root: new URL("..", import.meta.url),
    variable: "EXPO_PUBLIC_SPEC",
    origin: "SPEC_API_URL",
    locales: supportedLocales,
    catalogue: catalogueFacts(endpoints),
    views,
    reasons,
    validate: validateSpec,
    assets: [
        { path: "images/brand", brand: "images" },
        { path: "fonts", brand: "fonts" },
        { path: "videos", brand: "videos" },
        { path: "audios", brand: "audios" },
    ],
    architecture: {
        foundation: /^(react(?:\/|$)|expo(?:-[a-z-]+)?(?:\/|$)|@expo\/|engine\/)/,
        native: /^react-native(?:\/|$)/,
        free: ["elements", "icons", "hooks", "styles"],
        html: false,
        structure: ["render"],
        owners: {
            "lib/spec/config.ts": ["@spec/routing"],
            "lib/spec/runtime.ts": ["@spec/config", "@spec/schema", "@spec/messages", "@spec/client"],
            "lib/spec/world.ts": ["@spec/flags"],
            "lib/spec/emoji.ts": ["@spec/emoji"],
            "render/blocks.tsx": ["@spec/registry"],
        },
        layers: [
            ["lib/providers/", "api/core/", "types/", "../specs/"],
            ["api/features/"],
            ["lib/spec/"],
            ["lib/observe/"],
            ["stores/"],
            ["hooks/", /^features\/[^/]+\/hooks\//],
            ["elements/", "icons/", "styles/"],
            ["components/", /^features\/[^/]+\/components\//],
            ["features/"],
            ["render/"],
        ],
    },
});
export const { root, writeFile, writeJson, composeMessages, assets } = tools;
export const { installedSpecs, selectSpec, specFromEnvironment, loadSpec } = tools.loader;

export function checkLines (): void {

    const problems = sources.flatMap(( source ) => lineIssues(resolve(root, source), source, columns));

    if ( problems.length ) throw new Error(problems.join("\n"));

    report(`Lines: no source line is wider than ${columns} columns.`);

}

task(import.meta.url, async () => {

    await tools.check();
    checkLines();

});
