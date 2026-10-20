import { existsSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import type { Catalogue } from "@/lib/std/spec";
import { specGroup, specName } from "@/lib/std/validate";
import { compare, directories, entries, failure, guard } from "./core.ts";
import { type Features, viewFacts } from "./features.ts";
import { composeMessages, type Dictionaries } from "./messages.ts";

export type Validate<C, L extends string> = (
    identity: string,
    config: unknown,
    schema: unknown,
    messages: Dictionaries<L>,
    features: Features,
    catalogue: Catalogue,
) => C;
export type LoaderOptions<C, L extends string> = {
    root: string;
    variable: string;
    locales: readonly L[];
    brandFolders: readonly string[];
    catalogue: Catalogue;
    views: Readonly<Record<string, unknown>>;
    validate: Validate<C, L>;
    origin?: string | undefined;
};
export type Deployable = { contracts?: { urls?: Record<string, unknown>; options?: Record<string, unknown> } | null };
export type Loaded<C, L extends string> = C & { messages: Dictionaries<L>; identity: string; folder: string };
export type Loader<C, L extends string> = {
    installedSpecs: ( directory?: string ) => string[];
    selectSpec: ( value?: string, directory?: string ) => string;
    specFromEnvironment: () => string;
    loadSpec: ( path: string, directory?: string ) => Promise<Loaded<C, L>>;
};

const parts = ["config", "schema"];

export function identityOf ( path: string ): string {

    return path.slice(path.lastIndexOf("/") + 1);

}
export function deployedContracts ( config: unknown, origin: string | undefined ): unknown {

    const address = origin?.trim();

    if ( !address || !config || typeof config !== "object" ) return config;

    const { contracts } = config as Deployable;

    if ( !contracts ) return config;

    const urls = { ...contracts.urls, production: address, ...(contracts.urls?.browser === undefined ? {} : { browser: address }) };
    const options = address.startsWith("https://") ? { ...contracts.options, insecure: false } : contracts.options;

    return { ...config, contracts: { ...contracts, urls, options } };

}
function named ( value: string ): boolean {

    const segments = value.split("/");
    const leaf = segments.pop() ?? "";

    return specName.safeParse(leaf).success && segments.every(( segment ) => specGroup.safeParse(segment).success);

}
function discover ( directory: string, prefix = "" ): string[] {

    return directories(directory).flatMap(( name ) => {

        const path = prefix + name;
        const folder = resolve(directory, name);

        if ( specGroup.safeParse(name).success ) return discover(folder, `${path}/`);

        if ( !specName.safeParse(name).success ) throw new Error(`${folder} is neither a spec name nor a (group) folder.`);

        if ( !parts.some(( part ) => existsSync(resolve(folder, part))) )
            throw new Error(`${folder} has no config/ or schema/; a folder that only groups specs is written (${name}).`);

        return [path];

    });

}
function entry ( folder: string, part: string, directory: string ): string {

    const path = resolve(folder, part, "index.ts");

    if ( !existsSync(path) ) throw new Error(`${folder}/${part} must have an index.ts entry.`);

    return guard(directory, path, "Spec path escapes specs");

}
async function definition ( folder: string, part: string, directory: string ): Promise<unknown> {

    return ((await import(pathToFileURL(entry(folder, part, directory)).href)) as { default: unknown }).default;

}
function brandIssues ( folder: string, brandFolders: readonly string[] ): void {

    const path = resolve(folder, "brand");
    const unknown = (existsSync(path) ? entries(path) : [])
        .filter(( item ) => !item.name.startsWith(".") && !(item.isDirectory() && brandFolders.includes(item.name)))
        .map(( item ) => item.name);

    if ( unknown.length ) throw new Error(`brand/ holds only ${brandFolders.join(", ")}; found ${unknown.join(", ")}.`);

}
export function createLoader<C, L extends string> ( options: LoaderOptions<C, L> ): Loader<C, L> {

    const { root, variable, locales, brandFolders, catalogue, views, validate, origin } = options;
    const specs = resolve(root, "specs");
    const messages = resolve(root, "messages");
    const installedSpecs = ( directory = specs ): string[] =>
        discover(directory).sort(( a, b ) => compare(identityOf(a), identityOf(b)) || compare(a, b));
    const selectSpec = ( value = "", directory = specs ): string => {

        const asked = value.trim();
        const installed = installedSpecs(directory);

        if ( asked && !named(asked) ) {

            throw new Error(
                `${variable} names a spec folder: lowercase letters, numbers and hyphens, after an optional leading underscore, ` +
                    "behind its (group) folders when it has any.",
            );

        }

        const exact = installed.filter(( path ) => path === asked);
        const matches = asked ? (exact.length ? exact : installed.filter(( path ) => identityOf(path) === asked)) : installed.slice(0, 1);

        if ( matches.length > 1 ) throw new Error(`Spec "${asked}" lives in more than one group; name its folder: ${matches.join(", ")}.`);

        if ( !matches[0] ) {

            throw new Error(`Unknown or missing spec "${asked}" in ${directory}. Installed: ${installed.join(", ") || "(none)"}.`);

        }

        return matches[0];

    };
    const load = async ( identity: string, folder: string, directory: string ): Promise<Loaded<C, L>> => {

        const [config, schema] = await Promise.all([definition(folder, "config", directory), definition(folder, "schema", directory)]);
        const facts = viewFacts(views);

        brandIssues(folder, brandFolders);

        const dictionaries = composeMessages({ core: messages, brand: resolve(folder, "brand/messages"), locales });

        return {
            ...validate(identity, deployedContracts(config, origin ? process.env[origin] : undefined), schema, dictionaries, facts, catalogue),
            messages: dictionaries,
            identity,
            folder,
        };

    };

    return {
        installedSpecs,
        selectSpec,
        specFromEnvironment: () => {

            const mode = process.env.NODE_ENV ?? "development";
            const candidates = [
                `.env.${mode}.local`,
                ...(mode === "test" ? [] : [".env.local"]),
                `.env.${mode}`,
                ".env",
            ];

            for ( const candidate of candidates.map(( file ) => resolve(root, file)) ) {

                if ( existsSync(candidate) ) process.loadEnvFile(candidate);

            }

            return selectSpec(process.env[variable]);

        },
        loadSpec: async ( asked, directory = specs ) => {

            try {

                const path = selectSpec(asked, directory);

                return await load(identityOf(path), resolve(directory, path), directory);

            } catch ( error ) {

                throw new Error(`Invalid spec ${asked}: ${failure(error)}`);

            }

        },
    };

}
