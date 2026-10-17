import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { reasons } from "@/api/core";
import { endpoints } from "@/api/features";
import { type Locale, supportedLocales } from "@/lib/spec/languages";
import { type Compiled, validateSpec } from "@/lib/spec/surface";
import { catalogueFacts } from "@/lib/std/spec";
import { createTools, type Loaded, report, task, walk } from "@/lib/std/tooling";

export type Spec = Loaded<Compiled, Locale>;

const columns = 150;
const sources = ["src", "tools", "tests", "benches", "specs"];
const measured = /\.(?:ts|tsx|css)$/;
const literal = /#[0-9a-f]{3,8}\b|\b(?:rgb|hsl|oklch|color)a?\(|(?<![\w-])(?!0(?:\.0+)?(?![.\d]))\d*\.?\d+(?:px|rem|em|ms|s)\b/i;
const free = ["tokens.css"];

export const tools = createTools<Compiled, Locale>({
    root: new URL("..", import.meta.url),
    variable: "NEXT_PUBLIC_SPEC",
    origin: "SPEC_API_URL",
    locales: supportedLocales,
    catalogue: catalogueFacts(endpoints),
    reasons,
    validate: validateSpec,
    assets: [
        { path: "images/brand", brand: "images" },
        { path: "fonts", brand: "fonts" },
        { path: "videos", brand: "videos" },
        { path: "audios", brand: "audios" },
    ],
    architecture: {
        foundation: /^(react(?:\/|$)|next(?:\/|$)|server-only$)/,
        vendor: ["lib/providers/", "lib/std/"],
        html: true,
        owners: {
            "lib/spec/config.ts": ["@spec/routing", "@spec/settings", "@spec/build"],
            "lib/spec/runtime.ts": ["@spec/config", "@spec/schema", "@spec/messages"],
            "lib/spec/browser.ts": ["@spec/browser"],
            "app/(web)/[locale]/layout.tsx": ["@spec/theme.css"],
            "app/(web)/[locale]/[[...path]]/mount.ts": ["@spec/mount"],
            "app/(web)/[locale]/[[...path]]/warm.ts": ["@spec/preload"],
            "app/(web)/[locale]/[[...path]]/blocks.tsx": ["@spec/registry"],
        },
        layers: [
            ["lib/std/"],
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
            ["app/"],
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
export function lineIssues ( folder: string, prefix: string, limit = columns ): string[] {

    const files = walk(folder, ( entry, name ) => entry.isDirectory() && name === "lib/std/world/data");

    return files.filter(({ name }) => measured.test(name)).flatMap(({ path, name }) =>
        readFileSync(path, "utf8").split("\n").flatMap(( line, index ) =>
            line.length > limit ? [`${prefix}/${name}:${index + 1}: ${line.length} columns; the law is ${limit}.`] : [],
        ),
    );

}
export function checkLines (): void {

    const problems = sources.flatMap(( source ) => lineIssues(resolve(root, source), source));

    if ( problems.length ) throw new Error(problems.join("\n"));

    report(`Lines: no source line is wider than ${columns} columns.`);

}
export function checkStyles (): void {

    const problems = styleIssues(resolve(root, "src", "styles"), ["globals.css", "elements.css"]);

    if ( problems.length ) throw new Error(problems.join("\n"));

    report("Styles: every value outside tokens.css is a token.");

}

task(import.meta.url, async () => {

    await tools.check();
    checkStyles();
    checkLines();

});
