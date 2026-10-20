import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { unique } from "@/lib/std/array";
import { specGroup } from "@/lib/std/validate";
import { walk } from "./core.ts";

export type Rules = {
    source: string;
    specs: string;
    foundation: RegExp;
    native?: RegExp | undefined;
    free: readonly string[];
    vendor: readonly string[];
    html: boolean;
    markupFiles: RegExp;
    hookFiles: RegExp;
    featureEntry: RegExp;
    featureComponent: RegExp;
    extensions: readonly string[];
    helpers: readonly string[];
    structure: readonly string[];
    flat: readonly string[];
    markup: readonly string[];
    featureParts: readonly string[];
    apiParts: readonly string[];
    owners: Readonly<Record<string, readonly string[]>>;
    declarations: readonly string[];
    layer: ( path: string ) => number;
};
export type Sources = ReadonlyMap<string, string>;
export type Layer = readonly (string | RegExp)[];
export type SurfaceRules = {
    root: string;
    foundation: RegExp;
    native?: RegExp | undefined;
    free?: readonly string[] | undefined;
    vendor?: readonly string[] | undefined;
    html: boolean;
    structure?: readonly string[] | undefined;
    owners: Readonly<Record<string, readonly string[]>>;
    layers: readonly Layer[];
};
export type Analysis = { imports: string[]; types: string[]; issues: string[]; jsx: boolean };

type Scope = {
    path: string;
    element: boolean;
    vendor: boolean;
    spec: boolean;
    api: boolean;
    free: boolean;
    entry?: string | undefined;
    component?: string | undefined;
    leaf?: "element" | "icon" | "component" | undefined;
    name?: string | undefined;
};
type Graph = Map<string, string[]>;

const transpilers = {
    ts: new Bun.Transpiler({ loader: "ts", target: "browser" }),
    tsx: new Bun.Transpiler({ loader: "tsx", target: "browser" }),
};
const typeImport = /import\s+type\s+(?:[\s\S]*?)\s+from\s+["']([^"']+)["']/g;
const dynamicImport = /import\(\s*(?!["'])/;
const tag = /\bjsx(?:s|DEV)?(?:_\w+)?\(\s*"([a-z][a-z0-9-]*)"/g;
const styled = /\b(className|style)\s*:/g;
const rendering = /\bjsx(?:s|DEV)?(?:_\w+)?\(/;
const call = /(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(/g;
const branching = /\b(?:if|for|while|switch|function|await|class)\b|\bnew\s+[A-Za-z_$]|=>|\?[^.?]/;
const fetching = /(?<![\w$.])fetch\s*\(/;
const bags = new RegExp([
    /\bComponentProps(?:WithRef|WithoutRef)?\b/.source,
    /\b(?:All|Input|Button|Anchor|Html|HTML)\w*Attributes\b/.source,
    /\b(?:className|style)\??\s*:\s*(?:string|CSSProperties|React\.CSSProperties)\b/.source,
].join("|"));
const leaves = {
    element: /^(?:icons\/|lib\/std\/|lib\/providers\/|types\/)/,
    icon: /^(?:lib\/std\/|types\/)/,
} as const;

function leafOf ( path: string ): Scope["leaf"] {

    if ( path.startsWith("elements/") ) return "element";
    if ( path.startsWith("icons/") ) return "icon";

    return path.startsWith("components/") ? "component" : undefined;

}
function scopeOf ( path: string, rules: Rules ): Scope {

    return {
        path,
        element: rules.markup.some(( folder ) => path.startsWith(`${folder}/`)),
        vendor: rules.vendor.some(( folder ) => path.startsWith(folder)),
        spec: path.startsWith("../specs/"),
        api: path.startsWith("api/"),
        free: rules.free.some(( folder ) => path.startsWith(`${folder}/`)) || rules.vendor.some(( folder ) => path.startsWith(folder)),
        entry: rules.featureEntry.exec(path)?.[1],
        component: rules.featureComponent.exec(path)?.[1],
        leaf: leafOf(path),
        name: /^(?:elements|icons|components)\/([^/.]+)\.tsx?$/.exec(path)?.[1],
    };

}
function specHome ( path: string ): string {

    const segments = path.split("/");
    const leaf = segments.findIndex(( segment, index ) => index > 1 && !specGroup.safeParse(segment).success);

    return segments.slice(0, leaf + 1).join("/");

}
function leafIssues ( { leaf, name: own }: Scope, name: string, standard: string ): string[] {

    if ( !leaf || !(name.startsWith(".") || name.startsWith("@/")) ) return [];
    if ( leaf === "component" ) {

        const allowed = /^(?:elements|icons|components|types)\//.test(standard) || standard === `hooks/use-${own}`;

        return allowed ? [] : [`A component composes elements, icons, components and its own hook hooks/use-${own} only, not ${name}`];

    }

    const reach = leaf === "element" ? "icons, lib/std, lib/providers and types" : "lib/std and types";

    return leaves[leaf].test(standard) ? [] : [`An ${leaf} stands alone: it imports ${reach} only, not ${name}`];

}
function dependencyIssues ( scope: Scope, name: string, rules: Rules ): string[] {

    const { path, spec, vendor, entry, component, free } = scope;
    const selected = name.startsWith("@spec/");
    const target = name.startsWith(".") ? relative(rules.source, resolve(rules.source, dirname(path), name)) : "";
    const standard = name.startsWith("@/") ? relative(rules.source, resolve(rules.source, name.slice(2))) : target;
    const native = rules.native?.test(name) ?? false;
    const external = !(
        name.startsWith(".") ||
        name.startsWith("@/") ||
        selected ||
        rules.foundation.test(name) ||
        native
    );
    const own =
        entry !== undefined && (target.startsWith(`features/${entry}/components/`) || rules.foundation.test(name));
    const home = specHome(path);
    const door = name === "@/lib/spec/surface";

    return [
        ...(selected && !rules.owners[path]?.includes(name) ? ["Selected specs belong behind lib/spec."] : []),
        ...(external && !vendor ? [`Third-party imports belong in lib/providers: ${name}`] : []),
        ...(native && !free ? [`Native primitives belong in elements: ${name}`] : []),
        ...(spec && !door && !target.startsWith(`${home}/`)
            ? ["Specs import their own modules and @/lib/spec/surface only."]
            : []),
        ...(entry !== undefined && !own
            ? [`A feature entry is thin: it imports its own components only, not ${name}`]
            : []),
        ...(component !== undefined && standard.startsWith("elements/")
            ? [`Features build on components, not elements: ${name}`]
            : []),
        ...leafIssues(scope, name, standard.replace(/\.tsx?$/, "")),
    ];

}
function extensionIssues ( { path, spec }: Scope, jsx: boolean, rules: Rules ): string[] {

    if ( spec ) return [];

    const stem = path.replace(/\.[jt]sx?$/, "");
    const tsx = /\.tsx$/.test(path);

    if ( rules.markupFiles.test(stem) ) return tsx ? [] : ["Markup files end in .tsx."];
    if ( rules.hookFiles.test(path) ) return tsx || jsx ? ["Hooks are logic: a .ts file without markup."] : [];
    if ( jsx && !tsx ) return ["Markup belongs in a .tsx file."];

    return tsx && !jsx ? ["No markup here: a .ts file."] : [];

}
function markupIssues ( { element, api, vendor }: Scope, code: string, compiled: string, rules: Rules ): string[] {

    const issues: string[] = [];

    if ( fetching.test(code) && !api && !vendor ) issues.push("Backend transport belongs in src/api.");
    if ( element && bags.test(code) ) issues.push("Elements take semantic props only: className, style and HTML attribute bags are refused.");
    if ( element ) return issues;

    const tags = rules.html ? unique([...compiled.matchAll(tag)].map(( match ) => match[1] ?? "")) : [];
    const attributes = rendering.test(compiled)
        ? unique([...compiled.matchAll(styled)].map(( match ) => match[1] ?? ""))
        : [];

    if ( tags.length ) issues.push(`HTML belongs in elements: ${tags.join(", ")}`);
    if ( attributes.length ) issues.push(`Styling belongs in elements: ${attributes.join(", ")}`);

    return issues;

}
function specIssues ( { spec }: Scope, compiled: string, rules: Rules ): string[] {

    if ( !spec ) return [];

    const body = compiled.replace(/^\s*import[^\n]*$/gm, "");
    const calls = [...body.matchAll(call)]
        .map(( match ) => match[1] ?? "")
        .filter(( name ) => !rules.helpers.includes(name));

    return [
        ...(branching.test(body) ? ["Specs are declarative data; execution and branching belong in src."] : []),
        ...(calls.length ? [`Specs may call typed definition helpers only: ${unique(calls).join(", ")}`] : []),
    ];

}
function ownershipIssues (
    { entry }: Scope,
    code: string,
    imports: readonly string[],
    owner: string | undefined,
): string[] {

    if ( entry === undefined ) return [];

    const client = /^\s*["']use client["'];?/m.test(code.split("\n").slice(0, 3).join("\n"));
    const server = imports.includes("server-only");

    if ( !client && !server ) return ["Feature entries declare client or server ownership."];
    if ( owner === "client" && !client ) return ['The contract view says client; the entry must start with "use client".'];
    if ( owner === "server" && !server ) return ["The contract view says server; the entry must import server-only."];

    return [];

}
export function analyze ( path: string, code: string, rules: Rules, owner?: string ): Analysis {

    const scope = scopeOf(path, rules);
    const transpiler = path.endsWith(".tsx") ? transpilers.tsx : transpilers.ts;
    const scanned = transpiler.scan(code);
    const compiled = transpiler.transformSync(code);
    const imports = scanned.imports.map(( entry ) => entry.path);
    const types = [...code.matchAll(typeImport)]
        .map(( match ) => match[1] ?? "")
        .filter(( name ) => !imports.includes(name));
    const jsx = rendering.test(compiled);
    const issues = [
        ...(dynamicImport.test(code) && !scope.vendor ? ["Use explicit dynamic import paths."] : []),
        ...imports.flatMap(( name ) => dependencyIssues(scope, name, rules)),
        ...markupIssues(scope, code, compiled, rules),
        ...specIssues(scope, compiled, rules),
        ...ownershipIssues(scope, code, imports, owner),
        ...extensionIssues(scope, jsx, rules),
    ];

    return { imports, types, issues, jsx };

}
function code ( directory: string ): string[] {

    return walk(directory)
        .filter(( item ) => /\.tsx?$/.test(item.entry.name) && !item.entry.name.endsWith(".d.ts"))
        .map(( item ) => item.path);

}
export function readSources ( rules: Rules ): Map<string, string> {

    const paths = [...code(rules.source), ...code(rules.specs)];

    return new Map(paths.map(( path ) => [relative(rules.source, path), readFileSync(path, "utf8")]));

}
function targetOf ( path: string, name: string, sources: Sources, rules: Rules ): string | undefined {

    const local = name.startsWith(".") ? relative(rules.source, resolve(rules.source, dirname(path), name)) : null;
    const candidate = name.startsWith("@/") ? name.slice(2) : local;

    return candidate === null
        ? undefined
        : rules.extensions.map(( suffix ) => candidate + suffix).find(( value ) => sources.has(value));

}
function edgeIssues ( path: string, to: string, rules: Rules ): string[] {

    const inner = /^features\/([^/]+)\/(?:hooks|components)/.exec(to);
    const door = path.startsWith("../specs/") && to === "lib/spec/surface.ts";

    return [
        ...(to.startsWith("../specs/") && !path.startsWith("../specs/")
            ? [`${path}: direct spec import; use lib/spec.`]
            : []),
        ...(!door && rules.layer(to) > rules.layer(path) ? [`${path}: upward dependency on ${to}`] : []),
        ...(inner && !path.startsWith(`features/${inner[1]}/`)
            ? [`${path}: feature internals must stay private: ${to}`]
            : []),
    ];

}
function cycle ( graph: Graph, path: string, chain: string[], seen: Set<string>, problems: string[] ): void {

    if ( chain.includes(path) ) {

        problems.push(`Import cycle: ${[...chain, path].join(" -> ")}`);

        return;

    }

    if ( seen.has(path) ) return;

    seen.add(path);

    for ( const child of graph.get(path) ?? [] ) cycle(graph, child, [...chain, path], seen, problems);

}
function ownerOf ( path: string, sources: Sources ): string | undefined {

    const name = /^features\/([^/]+)\/index\.tsx$/.exec(path)?.[1];
    const manifest = name ? sources.get(`api/features/${name}.ts`) : undefined;

    return manifest ? /owner:\s*["'](server|client)["']/.exec(manifest)?.[1] : undefined;

}
export function inspect ( sources: Sources, rules: Rules ): string[] {

    const problems: string[] = [];
    const graph: Graph = new Map();
    const seen = new Set<string>();

    for ( const [path, text] of sources ) {

        const { imports, types, issues } = analyze(path, text, rules, ownerOf(path, sources));
        const edges = imports.flatMap(( name ) => targetOf(path, name, sources, rules) ?? []);
        const declared = rules.declarations.some(( entry ) => path.startsWith(entry));
        const shapes = declared ? [] : types.flatMap(( name ) => targetOf(path, name, sources, rules) ?? []);

        problems.push(
            ...issues.map(( issue ) => `${path}: ${issue}`),
            ...edges.flatMap(( to ) => edgeIssues(path, to, rules)),
            ...shapes
                .filter(( to ) => rules.layer(to) > rules.layer(path))
                .map(( to ) => `${path}: upward type dependency on ${to}`),
        );
        graph.set(path, edges);

    }

    for ( const path of graph.keys() ) cycle(graph, path, [], seen, problems);

    return problems;

}
