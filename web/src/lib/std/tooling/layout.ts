import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import type { Rules } from "./architecture.ts";

function featureIssues ( tree: string, name: string, rules: Rules ): string[] {

    const folder = `src/features/${name}/`;
    const parts = readdirSync(resolve(tree, "features", name), { withFileTypes: true }).filter(
        ( entry ) => !entry.name.startsWith("."),
    );
    const strangers = parts.filter(
        ( entry ) => !rules.featureParts.includes(entry.name) || entry.isDirectory() === entry.name.includes("."),
    );

    return [
        ...(existsSync(resolve(tree, "api", "features", `${name}.ts`)) ? [] : [`${folder} has no contract: src/api/features/${name}.ts`]),
        ...(parts.some(( entry ) => entry.name === "index.tsx") ? [] : [`${folder} needs its entry index.tsx`]),
        ...strangers.map(( entry ) => `${folder} holds ${rules.featureParts.join(", ")} only: ${entry.name}`),
    ];

}
export function layoutIssues ( rules: Rules, tree: string = rules.source ): string[] {

    const layers = readdirSync(tree)
        .filter(( entry ) => !rules.structure.includes(entry))
        .map(( entry ) => `src/ holds the fixed layers only: ${entry}`);
    const nesting = rules.flat.flatMap(( folder ) =>
        (existsSync(resolve(tree, folder)) ? readdirSync(resolve(tree, folder), { withFileTypes: true }) : [])
            .filter(( entry ) => entry.isDirectory())
            .map(( entry ) => `src/${folder}/ must stay flat: ${entry.name}`),
    );
    const features = existsSync(resolve(tree, "features"))
        ? readdirSync(resolve(tree, "features"), { withFileTypes: true })
              .filter(( entry ) => !entry.name.startsWith("."))
              .flatMap(( entry ) =>
                  entry.isDirectory()
                      ? featureIssues(tree, entry.name, rules)
                      : [`src/features/ contains feature directories only: ${entry.name}`],
              )
        : [];
    const api = readdirSync(resolve(tree, "api"), { withFileTypes: true })
        .filter(( entry ) => !entry.isDirectory() || !rules.apiParts.includes(entry.name))
        .map(( entry ) => `src/api/ holds ${rules.apiParts.join(", ")} only: ${entry.name}`);

    return [...layers, ...nesting, ...features, ...api];

}
export function viewIssues ( views: Readonly<Record<string, unknown>>, tree: string ): string[] {

    return Object.keys(views)
        .filter(( name ) => !existsSync(resolve(tree, "features", name, "index.tsx")))
        .map(( name ) => `src/api/features/${name}.ts declares a view, but src/features/${name}/index.tsx does not exist`);

}
