import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { catalogueFacts } from "engine/spec";
import { createTools, type Loaded, lineIssues, report, task, walk } from "engine/tooling";
import { reasons } from "@/api/core";
import { endpoints, views } from "@/api/features";
import { type Locale, supportedLocales } from "@/lib/spec/languages";
import { type Compiled, validateSpec } from "@/lib/spec/surface";

export type Spec = Loaded<Compiled, Locale>;

const columns = 150;
const sources = ["src", "tools", "tests", "benches", "specs"];
const literal = /#[0-9a-f]{3,8}\b|\b(?:rgb|hsl|oklch|color)a?\(|(?<![\w-])(?!0(?:\.0+)?(?![.\d]))\d*\.?\d+(?:px|rem|em|ms|s)\b/i;
const free = ["tokens.css"];
const arbitrary = /[\w:-]*\[[^\]\s]*\]/g;
const faded = /\b(?:bg|text|border|ring|outline|fill|stroke|from|via|to|shadow|decoration|caret|accent|divide|placeholder)-[\w-]+\/\d+/g;
const marked = ["elements", "icons"];

export const tools = createTools<Compiled, Locale>({
    root: new URL("..", import.meta.url),
    variable: "NEXT_PUBLIC_SPEC",
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
        foundation: /^(react(?:\/|$)|next(?:\/|$)|server-only$|engine\/)/,
        vendor: ["lib/providers/"],
        html: true,
        structure: ["proxy.server.ts"],
        owners: {
            "lib/spec/config.ts": ["@spec/routing", "@spec/settings"],
            "lib/spec/runtime.ts": ["@spec/config", "@spec/schema", "@spec/messages"],
            "lib/spec/browser.ts": ["@spec/browser"],
            "app/[locale]/layout.tsx": ["@spec/theme.css"],
            "app/[locale]/[[...path]]/mount.ts": ["@spec/mount"],
            "app/[locale]/[[...path]]/warm.ts": ["@spec/preload"],
            "app/[locale]/[[...path]]/blocks.tsx": ["@spec/registry"],
        },
        layers: [
            ["lib/providers/", "api/core/", "types/", "../specs/"],
            ["api/features/"],
            ["lib/spec/"],
            ["lib/seo/"],
            ["lib/observe/"],
            ["stores/"],
            ["hooks/", /^features\/[^/]+\/hooks\//],
            ["elements/", "icons/", "styles/"],
            ["components/", /^features\/[^/]+\/components\//],
            ["features/"],
            ["app/", "proxy.server.ts"],
        ],
    },
});
export const { root, writeFile, writeJson, composeMessages, assets } = tools;
export const { installedSpecs, selectSpec, specFromEnvironment, loadSpec } = tools.loader;

export function styleIssues ( folder: string, files: readonly string[] ): string[] {

    return files.filter(( file ) => !free.includes(file)).flatMap(( file ) => {

        const lines = readFileSync(resolve(folder, file), "utf8").split("\n");

        return lines.flatMap(( line, index ) => {

            if ( line.trimStart().startsWith("@media") || !literal.test(line) ) return [];

            return [`styles/${file}:${index + 1}: a raw value belongs in tokens.css, not here: ${line.trim()}`];

        });

    });

}
export function classIssues ( folder: string ): string[] {

    const files = marked.filter(( layer ) => existsSync(resolve(folder, layer))).flatMap(( layer ) =>
        walk(resolve(folder, layer))
            .filter(( item ) => item.name.endsWith(".tsx"))
            .map(( item ) => ({ ...item, layer })),
    );

    return files.flatMap(({ path, name, layer }) => readFileSync(path, "utf8").split("\n").flatMap(( line, index ) => {

        const raw = [...line.matchAll(arbitrary)].map(( found ) => found[0]).filter(( found ) => literal.test(found));
        const tinted = [...line.matchAll(faded)].map(( found ) => found[0]);

        return [...raw, ...tinted].map(( found ) => `src/${layer}/${name}:${index + 1}: a raw value belongs in tokens.css, not in a class: ${found}`);

    }));

}
export function checkLines (): void {

    const problems = sources.flatMap(( source ) => lineIssues(resolve(root, source), source, columns));

    if ( problems.length ) throw new Error(problems.join("\n"));

    report(`Lines: no source line is wider than ${columns} columns.`);

}
export function checkStyles (): void {

    const problems = [...styleIssues(resolve(root, "src", "styles"), ["globals.css"]), ...classIssues(resolve(root, "src"))];

    if ( problems.length ) throw new Error(problems.join("\n"));

    report("Styles: every value outside tokens.css is a token, in stylesheets and in element classes.");

}

task(import.meta.url, async () => {

    await tools.check();
    checkStyles();
    checkLines();

});
