import { describe, expect, test } from "bun:test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

type Manifest = { name: string; exports: Record<string, string> };

const root = resolve(import.meta.dir, "..");
const packages = resolve(root, "packages");
const manifest = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8")) as Manifest;
const members = readdirSync(packages, { withFileTypes: true }).filter(( entry ) => entry.isDirectory()).map(( entry ) => entry.name).sort();
const reach = /from\s+"engine\/([a-z]+)"|import\(\s*"engine\/([a-z]+)"\s*\)/g;
const owned = ["package.json", "node_modules"];
const crossing = /from\s+"\.\.\/\.\.\/|import\(\s*"\.\.\/\.\.\//;

function sources ( member: string ): string[] {

    const folder = resolve(packages, member, "src");

    return readdirSync(folder).filter(( name ) => /\.tsx?$/.test(name)).map(( name ) => readFileSync(resolve(folder, name), "utf8"));

}
function graph (): Map<string, Set<string>> {

    return new Map(members.map(( member ) => {

        const used = sources(member).flatMap(( code ) => [...code.matchAll(reach)].map(( found ) => found[1] ?? found[2] ?? ""));

        return [member, new Set(used.filter(( name ) => name !== member))];

    }));

}
function cycle ( edges: Map<string, Set<string>> ): string[] {

    const state = new Map<string, number>();
    const trail: string[] = [];

    function visit ( node: string ): string[] {

        if ( state.get(node) === 1 ) return [...trail.slice(trail.indexOf(node)), node];
        if ( state.get(node) === 2 ) return [];

        state.set(node, 1);
        trail.push(node);

        for ( const next of [...(edges.get(node) ?? [])].sort() ) {

            const found = visit(next);

            if ( found.length ) return found;

        }

        trail.pop();
        state.set(node, 2);

        return [];

    }

    for ( const node of [...edges.keys()].sort() ) {

        const found = visit(node);

        if ( found.length ) return found;

    }

    return [];

}

describe("the engine members", () => {

    test("every member is one folder with an index and no manifest or node_modules, exported once under its own name", () => {

        const exported = Object.keys(manifest.exports).filter(( key ) => key !== "./package.json").map(( key ) => key.slice(2)).sort();

        expect(manifest.name).toBe("engine");
        expect(exported).toEqual(members);
        expect(members.filter(( member ) => !existsSync(resolve(packages, member, "src", "index.ts")))).toEqual([]);
        expect(members.filter(( member ) => manifest.exports[`./${member}`] !== `./packages/${member}/src/index.ts`)).toEqual([]);
        expect(members.filter(( member ) => owned.some(( name ) => existsSync(resolve(packages, member, name))))).toEqual([]);

    });
    test("members reach each other only through engine/<member>, only existing ones, and never in a cycle", () => {

        const edges = graph();
        const unknown = [...edges].flatMap(( [member, used] ) =>
            [...used].filter(( name ) => !members.includes(name)).map(( name ) => `${member} → ${name}`),
        );
        const escaped = members.filter(( member ) => sources(member).some(( code ) => crossing.test(code)));

        expect(unknown).toEqual([]);
        expect(escaped).toEqual([]);
        expect(cycle(edges)).toEqual([]);

    });

});
